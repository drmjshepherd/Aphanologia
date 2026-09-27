from fastapi import FastAPI, HTTPException, Query, Path, Depends, UploadFile, File
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from typing import Optional, List
from database import get_db_connection
import json
import re
import os
import io
from openpyxl import Workbook, load_workbook
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.comments import Comment
from dotenv import load_dotenv
from starlette.middleware.sessions import SessionMiddleware
from authlib.integrations.starlette_client import OAuth
from starlette.requests import Request
from starlette.responses import RedirectResponse

load_dotenv()  # reads the .env file into memory so os.environ can see it

app = FastAPI(
    title="Aphanologia Acari Portal API",
    description="Spatial API endpoints serving British Acari records & PostGIS geometries",
    version="1.1.0"
)

# Session middleware lets us securely remember who's logged in between
# page requests, using a signed cookie in the visitor's browser. The
# secret key (from .env) is what makes this cookie tamper-proof - a
# visitor can't edit their own cookie to pretend to be someone else,
# since they don't know the key used to sign it.
app.add_middleware(SessionMiddleware, secret_key=os.environ["SESSION_SECRET_KEY"])

# Serves shared front-end assets used across multiple pages - e.g.
# static/js/literature_widget.js, the embeddable "find or add a
# literature reference" component used by the taxonomy editor and
# (eventually) the sample submission form, so that widget only has
# to be written and maintained once.
app.mount("/static", StaticFiles(directory="static"), name="static")

# Sets up the connection to Google's sign-in system using the
# credentials from .env. server_metadata_url points Authlib at
# Google's own published configuration, so it automatically knows
# the correct URLs/settings to use - we don't have to hardcode them.
oauth = OAuth()
oauth.register(
    name='google',
    client_id=os.environ["GOOGLE_CLIENT_ID"],
    client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

# checks to see if the user is allowed to submit records

def require_contributor(request: Request):
    """
    Reusable permission check for any endpoint that lets someone
    create or edit their own data. Raises a 401 (not logged in) or
    403 (logged in, but role too low) error automatically if the
    check fails - the endpoint's own code never runs in that case.
    Returns the logged-in user's session info if the check passes.
    """
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="You must be signed in to do this")
    if user["role"] not in ("contributor", "superuser", "hyperuser"):
        raise HTTPException(status_code=403, detail="Your account needs contributor access to submit records")
    return user

def require_superuser(request: Request):
    """
    Same pattern as require_contributor, but for tools that should
    only be available to trusted admins - e.g. the
    schema viewer, and later the review/approval screen. Deliberately
    a separate function (rather than reusing require_contributor with
    a different role list) so each endpoint's permission requirement
    is obvious at a glance from which dependency it uses.
    """
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="You must be signed in to do this")
    if user["role"] not in ("superuser", "hyperuser"):
        raise HTTPException(status_code=403, detail="This tool is restricted to superusers")
    return user

@app.get("/", response_class=FileResponse)
def serve_landing():
    return FileResponse("landing.html")

@app.get("/map", response_class=FileResponse)
def serve_map():
    return FileResponse("index.html")

@app.get("/taxonomy", response_class=FileResponse)
def serve_taxonomy():
    return FileResponse("taxonomy.html")

@app.get("/submit", response_class=FileResponse)
def serve_submit():
    return FileResponse("submit.html")

@app.get("/literature", response_class=FileResponse)
def serve_literature():
    return FileResponse("literature.html")

@app.get("/records/view", response_class=FileResponse)
def serve_record_viewer():
    return FileResponse("record_viewer.html")

@app.get("/batch/upload", response_class=FileResponse)
def serve_batch_upload():
    return FileResponse("batch_upload.html")

@app.get("/admin/schema", response_class=FileResponse)
def serve_schema_viewer():
    return FileResponse("schema.html")

@app.get("/review", response_class=FileResponse)
def serve_review():
    return FileResponse("review.html")

@app.get("/admin/taxonomy", response_class=FileResponse)
def serve_taxonomy_editor():
    return FileResponse("taxonomy_editor.html")

@app.get("/admin/records", response_class=FileResponse)
def serve_record_editor():
    return FileResponse("record_editor.html")


#==========================================================
# LOGIN ENDPOINTS
#==========================================================

@app.get("/auth/login")
async def login(request: Request):
    """
    Step 1: sends the visitor to Google's own sign-in page. redirect_uri
    tells Google where to send them back to afterward - this MUST
    exactly match what you registered in Google Cloud Console.
    """
    redirect_uri = "http://127.0.0.1:8000/auth/callback"
    return await oauth.google.authorize_redirect(request, redirect_uri)


@app.get("/auth/callback")
async def auth_callback(request: Request):
    """
    Step 2: Google sends the visitor back here after they approve
    sign-in. Verifies the token is genuine, extracts their email/name,
    then looks them up (or creates them) in our own users table -
    this is the moment authentication (Google) hands off to our own
    authorization system (the role stored in our database).
    """
    token = await oauth.google.authorize_access_token(request)
    userinfo = token.get('userinfo')

    if not userinfo:
        raise HTTPException(status_code=400, detail="Could not verify Google sign-in")

    google_sub = userinfo["sub"]
    email = userinfo["email"]
    display_name = userinfo.get("name", email)

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT user_id, role FROM users WHERE google_sub = %s;', (google_sub,))
        existing = cursor.fetchone()

        if existing:
            cursor.execute(
                'UPDATE users SET last_login_at = CURRENT_TIMESTAMP, email = %s, display_name = %s WHERE google_sub = %s;',
                (email, display_name, google_sub)
            )
            user_id, role = existing["user_id"], existing["role"]
        else:
            cursor.execute(
                '''INSERT INTO users (google_sub, email, display_name, last_login_at)
                   VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                   RETURNING user_id, role;''',
                (google_sub, email, display_name)
            )
            new_row = cursor.fetchone()
            user_id, role = new_row["user_id"], new_row["role"]

        conn.commit()
    finally:
        cursor.close()
        conn.close()

    # Store the essentials in the visitor's session (the secure cookie).
    # Every future request from this browser can now check
    # request.session.get("user") to know who's logged in, without
    # querying Google again.
    request.session["user"] = {
        "user_id": user_id,
        "email": email,
        "display_name": display_name,
        "role": role,
    }

    return RedirectResponse(url="/")


@app.get("/auth/logout")
async def logout(request: Request):
    """Clears the session, signing the visitor out."""
    request.session.pop("user", None)
    return RedirectResponse(url="/")


@app.get("/api/v1/auth/me")
async def get_current_user(request: Request):
    """
    Lets the front end (any page) check who's currently logged in,
    so it can show 'Sign in' vs. the person's name/role appropriately.
    """
    user = request.session.get("user")
    if not user:
        return {"logged_in": False}
    return {"logged_in": True, **user}


# ==========================================================
# TAXONOMY BROWSER ENDPOINTS
# ==========================================================
# These four endpoints feed the drill-down taxonomy tree.
# Each one is deliberately small: it answers one narrow
# question, so the front-end can call them one at a time
# as the user clicks to expand branches.

@app.get("/api/v1/taxonomy/root")
def get_taxonomy_root():
    """
    Returns the top-level taxon/taxa to start the tree from
    (normally just Kingdom Animalia). Field names deliberately
    match get_immediate_children()'s output so the front-end
    tree code can treat every level identically.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT
                t."taxonID" AS taxon_id,
                t."scientificName" AS scientific_name,
                t."scientificnameAuthorship" AS authorship,
                t."taxonrank" AS taxon_rank,
                t."taxonomicStatus" AS taxonomic_status,
                EXISTS (
                    SELECT 1 FROM taxonomy c
                    WHERE c."parentNameUsageID" = t."taxonID"
                      AND c."acceptedNameUsageID" IS NULL
                ) AS has_children,
                EXISTS (
                    SELECT 1 FROM taxonomy s
                    WHERE s."acceptedNameUsageID" = t."taxonID"
                ) AS has_synonyms
            FROM taxonomy t
            WHERE t."parentNameUsageID" IS NULL
              AND t."acceptedNameUsageID" IS NULL
            ORDER BY t."scientificName";
        """)
        rows = cursor.fetchall()
        return {"count": len(rows), "taxa": rows}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query error: {str(e)}")
    finally:
        cursor.close()
        conn.close()

@app.get("/api/v1/taxonomy/children/{taxon_id}")
def get_taxonomy_children(taxon_id: str = Path(..., description="The taxonID to fetch children for")):
    """
    Returns the immediate hierarchical children of a given taxon
    (e.g. a family returns its subfamilies; a genus returns its
    species). Uses the get_immediate_children() SQL function
    created earlier (Query-2). Each returned taxon also says
    whether IT has further children and/or synonyms, so the
    front end knows whether to draw an expand arrow.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM get_immediate_children(%s);", (taxon_id,))
        rows = cursor.fetchall()
        return {"parent_taxon_id": taxon_id, "count": len(rows), "children": rows}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query error: {str(e)}")
    finally:
        cursor.close()
        conn.close()


@app.get("/api/v1/taxonomy/synonyms/{taxon_id}")
def get_taxonomy_synonyms(taxon_id: str = Path(..., description="The taxonID to fetch synonyms for")):
    """
    Returns known synonyms (and pinned misapplications) of a given
    species-or-lower taxon. Uses get_synonyms() (Query-3). Will
    simply return an empty list for genus and above, since
    synonymy isn't recorded above species rank in this database.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM get_synonyms(%s);", (taxon_id,))
        rows = cursor.fetchall()
        return {"accepted_taxon_id": taxon_id, "count": len(rows), "synonyms": rows}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query error: {str(e)}")
    finally:
        cursor.close()
        conn.close()


@app.get("/api/v1/taxonomy/detail/{taxon_id}")
def get_taxonomy_detail(taxon_id: str = Path(..., description="The taxonID to fetch details for")):
    """
    Returns full information about a single taxon, for display
    in the details panel when a user clicks a name in the tree.
    Includes the taxon's own record, plus (if relevant) the name
    and ID of what it resolves to (its accepted name), and the
    name of its direct parent, so the panel can show readable
    text rather than raw ID numbers.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT
                t."taxonID",
                t."scientificName",
                t."scientificnameAuthorship",
                t."taxonrank",
                t."taxonomicStatus",
                t."nomenclaturalStatus",
                t."taxonRemarks",
                t."parentNameUsageID",
                parent."scientificName" AS parent_scientific_name,
                t."acceptedNameUsageID",
                accepted."scientificName" AS accepted_scientific_name
            FROM taxonomy t
            LEFT JOIN taxonomy parent ON t."parentNameUsageID" = parent."taxonID"
            LEFT JOIN taxonomy accepted ON t."acceptedNameUsageID" = accepted."taxonID"
            WHERE t."taxonID" = %s;
        """, (taxon_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"No taxon found with taxonID {taxon_id}")
        return row
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query error: {str(e)}")
    finally:
        cursor.close()
        conn.close()

@app.get("/api/v1/taxonomy/search")
def search_taxonomy(
    q: str = Query(..., min_length=3, description="Search text (minimum 3 characters). Separate alternative searches with OR; space-separated words within a search are combined with AND."),
    limit: int = Query(25, ge=1, le=50, description="Maximum number of matches to return"),
    valid_only: bool = Query(False, description="If true, only return taxa with taxonomicStatus = 'accepted' (excludes synonyms, misapplied and doubtful names)")
):
    """
    Searches every taxon name in the database in one go - accepted
    names, doubtful names, misapplied names, and synonyms all live
    in the same taxonomy table, so this naturally covers all of them
    (unless valid_only excludes anything but accepted names - used by
    the "Only allow valid taxa" toggle on the sample submission form,
    since working through literature often means recording a species
    under a name the DB itself has since synonymised, which
    valid_only would otherwise hide).

    Two layers of matching:
      1. The existing boolean logic - split on 'OR', AND together the
         space-separated words within each group. This stays exact
         (no typo tolerance) and is the primary match.
      2. A fuzzy trigram fallback on the whole query, so a misspelled
         search still surfaces close matches even when the boolean
         match finds nothing.

    Results are ranked with an exact-prefix match first (so searching
    "Nothrus" surfaces the genus Nothrus itself before the many
    Ameronothrus species that merely contain "nothrus" mid-word),
    then by trigram similarity to the query, then alphabetically.
    """
    or_groups = [g.strip() for g in re.split(r'\bOR\b', q, flags=re.IGNORECASE) if g.strip()]
    if not or_groups:
        return {"query": q, "count": 0, "results": []}

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        group_clauses = []
        params = []
        for group in or_groups:
            words = [w for w in group.split() if w]
            if not words:
                continue
            word_clauses = []
            for word in words:
                word_clauses.append('"scientificName" ILIKE %s')
                params.append(f"%{word}%")
            group_clauses.append("(" + " AND ".join(word_clauses) + ")")

        if not group_clauses:
            return {"query": q, "count": 0, "results": []}

        boolean_where_sql = " OR ".join(group_clauses)

        # Fuzzy fallback uses the whole query string (not split into
        # words/groups) against the trigram index - this is what
        # catches typos the exact boolean matching above would miss.
        where_sql = f"({boolean_where_sql}) OR (\"scientificName\" %% %s)"
        params.append(q)

        if valid_only:
            where_sql = f"({where_sql}) AND \"taxonomicStatus\" = 'accepted'"

        # Ranking: exact prefix match first, then trigram similarity,
        # then alphabetical as a final tiebreaker
        params_for_order = [f"{q}%", q]

        sql = f"""
            SELECT
                "taxonID" AS taxon_id,
                "scientificName" AS scientific_name,
                "scientificnameAuthorship" AS authorship,
                "taxonrank" AS taxon_rank,
                "taxonomicStatus" AS taxonomic_status
            FROM taxonomy
            WHERE {where_sql}
            ORDER BY
                CASE WHEN "scientificName" ILIKE %s THEN 0 ELSE 1 END,
                similarity("scientificName", %s) DESC,
                "scientificName" ASC
            LIMIT %s;
        """
        params = params + params_for_order + [limit]

        cursor.execute(sql, params)
        rows = cursor.fetchall()
        return {"query": q, "count": len(rows), "results": rows}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query error: {str(e)}")
    finally:
        cursor.close()
        conn.close()


@app.get("/api/v1/taxonomy/path/{taxon_id}")
def get_taxonomy_path(taxon_id: str = Path(..., description="The taxonID to find the tree path for")):
    """
    Given any taxonID - including a synonym's - returns the ordered
    chain of hierarchy taxonIDs from the top of the tree (Animalia)
    down to the hierarchical node that the front-end tree needs to
    expand to reveal it. Wraps get_ancestor_chain() (Query-4).
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM get_ancestor_chain(%s);", (taxon_id,))
        rows = cursor.fetchall()
        if not rows:
            raise HTTPException(status_code=404, detail=f"No taxon found with taxonID {taxon_id}")
        ordered_ids = [r["taxon_id"] for r in rows]
        return {"taxon_id": taxon_id, "chain": ordered_ids}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query error: {str(e)}")
    finally:
        cursor.close()
        conn.close()
        
@app.get("/api/v1/taxonomy/photos/{taxon_id}")
def get_taxonomy_photos(
    taxon_id: str = Path(..., description="The taxonID to fetch a photo preview for"),
    limit: int = Query(8, ge=1, le=30, description="Maximum number of preview photos to return")
):
    """
    Returns a SMALL PREVIEW selection of photos for a taxon and
    everything beneath it - intended for the details panel, not a
    full gallery.

    Selection preference: photos whose filename-derived caption
    contains 'composite' (stacked focal-plane images, generally
    clearer/more representative) are preferred; remaining slots are
    filled with a random selection of the rest. This also caps how
    many rows the database considers per request, so selecting a
    huge group like Animalia stays cheap even though it may match
    tens of thousands of photos.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            WITH descendant_taxa AS (
                SELECT taxon_id FROM get_descendant_taxon_ids(%s)
            ),
            composites AS (
                SELECT m.media_id, m.link_level, m.caption, m.photographer, m.community_votes
                FROM view_media_with_resolved_taxon m
                WHERE m.effective_taxon_id IN (SELECT taxon_id FROM descendant_taxa)
                  AND m.caption ILIKE '%%composite%%'
                ORDER BY m.community_votes DESC
                LIMIT %s
            ),
            remainder AS (
                SELECT m.media_id, m.link_level, m.caption, m.photographer, m.community_votes
                FROM view_media_with_resolved_taxon m
                WHERE m.effective_taxon_id IN (SELECT taxon_id FROM descendant_taxa)
                  AND m.media_id NOT IN (SELECT media_id FROM composites)
                ORDER BY random()
                LIMIT %s
            )
            SELECT * FROM composites
            UNION ALL
            SELECT * FROM remainder
            LIMIT %s;
        """, (taxon_id, limit, limit, limit))
        rows = cursor.fetchall()
        return {"taxon_id": taxon_id, "count": len(rows), "photos": rows, "is_preview": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query error: {str(e)}")
    finally:
        cursor.close()
        conn.close()       
        
@app.get("/api/v1/taxonomy/literature/{taxon_id}")
def get_taxon_literature(taxon_id: str = Path(..., description="The taxonID to fetch linked literature for")):
    """
    Returns the literature references linked to a taxon via
    taxonomy_literature_junction, grouped by relationship type
    (taxonomy/synonymy source, name first published in, as used in,
    presence in UK from, identification key), each formatted as a
    single readable citation string with a clickable link where
    sourceURL is available.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT
                j."Type" AS relationship_type,
                l."sourceURL" AS url,
                CONCAT_WS(', ',
                    NULLIF(l."authorName", ''),
                    NULLIF(l."yearPublished", ''),
                    NULLIF(NULLIF(CONCAT('"', l."articleTitle", '"'), '""'), '"null"'),
                    NULLIF(l."publicationTitle", ''),
                    NULLIF(l."publicationSeries", ''),
                    NULLIF(NULLIF(CONCAT('Vol. ', l."publicationVolume"), 'Vol. '), 'Vol. null'),
                    NULLIF(NULLIF(CONCAT('No. ', l."publicationIssue"), 'No. '), 'No. null'),
                    NULLIF(NULLIF(CONCAT('pp. ', l."publicationPages"), 'pp. '), 'pp. null'),
                    NULLIF(NULLIF(CONCAT('ISBN/ISSN: ', l."publicationISBNorISSN"), 'ISBN/ISSN: '), 'ISBN/ISSN: null'),
                    NULLIF(NULLIF(CONCAT('DOI: ', l."publicationDOI"), 'DOI: '), 'DOI: null')
                ) AS formatted_ref
            FROM taxonomy_literature_junction j
            JOIN literature l ON j."litID" = l."litID"
            WHERE j.taxonid = %s
            ORDER BY j."Type", l."yearPublished" DESC, l."authorName" ASC;
        """, (taxon_id,))

        rows = cursor.fetchall()
        grouped = {
            "Taxonomy or synonymy from": [],
            "Name first published in": [],
            "As used in": [],
            "Presence in UK from": [],
            "Identification Key": []
        }
        for row in rows:
            rel_type = row["relationship_type"]
            if rel_type in grouped:
                grouped[rel_type].append({
                    "formatted_ref": row["formatted_ref"],
                    "url": row["url"]
                })
        return {"literature": grouped}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query error: {str(e)}")
    finally:
        cursor.close()
        conn.close()


# ===============================================================
# MEDIA RETRIEVAL FROM IMAGE ARCHIVE FILE STRUCTURE
# ===============================================================
from fastapi.responses import FileResponse

# The one place in the whole app that knows where image files actually
# live right now. Currently: your local OneDrive-synced folder, which
# Windows will transparently download from the cloud on first request
# (no need to pre-download the whole 77GB archive). When hosting moves
# to proper cloud storage later, only this function needs to change -
# every URL the website already generated will keep working exactly
# as before.
MEDIA_ROOT = r"C:\Users\Matth\OneDrive\Soil Biodiversity UK\Mesofauna Image Archive"

@app.get("/api/v1/media/{media_id}")
def get_media_file(media_id: int = Path(..., description="The media_id from observation_media")):
    """
    Serves the actual image file for a given photo record.
    Looks up the stored relative path, then serves it from wherever
    MEDIA_ROOT currently points.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT file_url FROM observation_media WHERE media_id = %s;', (media_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="No such photo")

        full_path = os.path.join(MEDIA_ROOT, row["file_url"])
        if not os.path.isfile(full_path):
            raise HTTPException(status_code=404, detail="Photo file not found on disk (may still be syncing from OneDrive, or the archive has moved)")

        return FileResponse(full_path)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error serving media: {str(e)}")
    finally:
        cursor.close()
        conn.close()


# ==========================================================
# MAP / OBSERVATIONS ENDPOINT
# ==========================================================

@app.get("/api/v1/observations/geojson")
def get_observations_geojson(
    limit: int = Query(5000, description="Maximum number of spatial points to return", ge=1, le=50000),
    taxon_id: Optional[str] = Query(None, description="Filter records to this taxon and everything beneath it (families, genera, species, synonyms, etc.)"),
    taxon_name: Optional[str] = Query(None, description="[Legacy] Filter records by plain text match on scientific name. Prefer taxon_id where possible."),
    exact_taxon_id: Optional[str] = Query(None, description="Filter records to exactly this taxonID as originally recorded, bypassing accepted-name/descendant resolution - used to isolate records entered under one specific synonym or misapplied name."),
    start_year: Optional[int] = Query(None, description="Filter records from this year onward"),
    end_year: Optional[int] = Query(None, description="Filter records up to this year")
):
    """
    Queries PostGIS and converts sample/observation points into a
    GeoJSON FeatureCollection.

    Date filtering note: earliestDateCollected / latestDateCollected
    are stored as TEXT (not a true date type), specifically so that
    dates before 1900 can be recorded without issue. They are always
    in YYYY-MM-DD format, so the year is reliably the first 4
    characters - we compare on that directly rather than using
    Postgres's date functions, which only work on genuine date columns.

    Some records only have one of the two date fields filled in
    (e.g. an old record dated only "by 1927"). To avoid silently
    excluding these, we treat whichever date IS present as standing
    in for the other when checking for an overlap with the
    requested year range.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        sql = """
            SELECT
                veo."observationID",
                veo."resolved_scientific_name" AS "scientificName",
                veo."resolved_taxon_rank" AS "taxonrank",
                veo."eventID",
                s."earliestDateCollected",
                s."latestDateCollected",
                s."samplingLocation",
                s."gridRef",
                ST_AsGeoJSON(s.geom_wgs84)::json AS geometry
            FROM view_effective_observations veo
            JOIN samples s ON veo."eventID" = s."eventID"
            WHERE s.geom_wgs84 IS NOT NULL
        """
        params = []

        if exact_taxon_id and exact_taxon_id.strip():
            sql += ' AND veo.raw_effective_taxon_id = %s'
            params.append(exact_taxon_id.strip())
        elif taxon_id and taxon_id.strip():
            sql += """ AND veo.resolved_taxon_id IN (
                SELECT taxon_id FROM get_descendant_taxon_ids(%s)
            )"""
            params.append(taxon_id.strip())
        elif taxon_name and taxon_name.strip():
            sql += " AND veo.\"resolved_scientific_name\" ILIKE %s"
            params.append(f"%{taxon_name.strip()}%")

        if start_year:
            # Include the record if its LATEST known date is on or
            # after the requested start year. Falls back to the
            # earliest date if latest is blank.
            sql += """ AND CAST(
                LEFT(COALESCE(NULLIF(s."latestDateCollected", ''), NULLIF(s."earliestDateCollected", '')), 4)
                AS INTEGER
            ) >= %s"""
            params.append(start_year)

        if end_year:
            # Include the record if its EARLIEST known date is on or
            # before the requested end year. Falls back to the
            # latest date if earliest is blank.
            sql += """ AND CAST(
                LEFT(COALESCE(NULLIF(s."earliestDateCollected", ''), NULLIF(s."latestDateCollected", '')), 4)
                AS INTEGER
            ) <= %s"""
            params.append(end_year)

        sql += " LIMIT %s;"
        params.append(limit)

        cursor.execute(sql, params)
        rows = cursor.fetchall()

        features = []
        for row in rows:
            if row["geometry"]:
                feature = {
                    "type": "Feature",
                    "geometry": row["geometry"],
                    "properties": {
                        "observationID": row["observationID"],
                        "scientificName": row["scientificName"],
                        "taxonRank": row["taxonrank"],
                        "eventID": row["eventID"],
                        "earliestDate": row["earliestDateCollected"],
                        "latestDate": row["latestDateCollected"],
                        "samplingLocation": row["samplingLocation"],
                        "gridRef": row["gridRef"]
                    }
                }
                features.append(feature)

        return {
            "type": "FeatureCollection",
            "count": len(features),
            "features": features
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query error: {str(e)}")
    finally:
        cursor.close()
        conn.close()


@app.get("/api/v1/records/view/{observation_id}")
def get_public_record_view(observation_id: str):
    """
    Public, read-only view of a full record: sample, observation,
    demographic groups and their specimens, and literature links at
    both levels - powers /records/view, reachable from the map
    popup's "View Record" link. Not gated behind login; everything
    returned here is the kind of thing a specimen label or a GBIF
    occurrence page would already show.

    Note: this does not currently redact anything based on
    samples.datarestricted - if some samples need coordinates or
    other details withheld from the public view for sensitive-species
    reasons, that's a deliberate follow-up worth designing rather
    than assuming here.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT o."observationID", o."eventID", o."taxonID", t."scientificName" AS taxon_name,
                   t."scientificnameAuthorship" AS taxon_authorship, t."taxonrank" AS taxon_rank,
                   o."identifiedBy", o."identificationVerificationStatus", o."identificationRemarks",
                   o."collectionID", o."catalogNumber", o."basisOfRecord", o."idTechnique",
                   o."idText[free_text]" AS "idText", o."occurrenceRemarks",
                   o.verification_status, o.verified_by, o.verified_date,
                   o.share_with_nbn, o.share_with_gbif,
                   o.entered_by, o.entered_at
            FROM observations o
            LEFT JOIN taxonomy t ON o."taxonID" = t."taxonID"
            WHERE o."observationID" = %s;
        """, (observation_id,))
        obs = cursor.fetchone()
        if not obs:
            raise HTTPException(status_code=404, detail=f"No observation found with observationID {observation_id}")

        cursor.execute('SELECT * FROM samples WHERE "eventID" = %s;', (obs["eventID"],))
        sample = cursor.fetchone()

        cursor.execute("""
            SELECT * FROM observation_demographics WHERE "observationID" = %s ORDER BY "demographicID";
        """, (observation_id,))
        demographics = cursor.fetchall()
        for d in demographics:
            cursor.execute('SELECT * FROM specimens WHERE "demographicID" = %s ORDER BY "specimenID";', (d["demographicID"],))
            d["specimens"] = cursor.fetchall()

        cursor.execute("""
            SELECT j.type, CONCAT_WS(', ', l."authorName", l."yearPublished", l."articleTitle", l."publicationTitle") AS formatted_ref, l."sourceURL"
            FROM observation_literature_junction j
            JOIN literature l ON j."litID" = l."litID"
            WHERE j."observationID" = %s;
        """, (observation_id,))
        obs_literature = cursor.fetchall()

        cursor.execute("""
            SELECT j."Type" AS type, CONCAT_WS(', ', l."authorName", l."yearPublished", l."articleTitle", l."publicationTitle") AS formatted_ref, l."sourceURL"
            FROM sample_literature_junction j
            JOIN literature l ON j."litID" = l."litID"
            WHERE j."eventID" = %s;
        """, (obs["eventID"],))
        sample_literature = cursor.fetchall()

        cursor.execute("""
            SELECT p.project_name, j.type
            FROM sample_project_junction j
            JOIN recording_projects p ON j.project_id = p.project_id
            WHERE j."eventID" = %s;
        """, (obs["eventID"],))
        sample_projects = cursor.fetchall()

        return {
            "observation": obs,
            "sample": sample,
            "demographics": demographics,
            "observation_literature": obs_literature,
            "sample_literature": sample_literature,
            "sample_projects": sample_projects
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query error: {str(e)}")
    finally:
        cursor.close()
        conn.close()

        
#==========================================================
# SUBMISSION ENDPOINTS
#==========================================================
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class SampleSubmission(BaseModel):
    samplingLocation: Optional[str] = None
    decimalLatitude: Optional[float] = None
    decimalLongitude: Optional[float] = None
    coordinateUncertaintyInMeters: Optional[int] = None
    earliestDateCollected: Optional[str] = None  # expects YYYY-MM-DD text, matching existing convention
    latestDateCollected: Optional[str] = None
    habitat: Optional[str] = None
    microhabitat: Optional[str] = None
    SHADe: Optional[str] = None  # e.g. "TsSc-5-6-5" - built by the guided SHADe picker on the submission form
    samplingProtocol: Optional[str] = None
    samplesizeValue: Optional[float] = None
    samplesizeUnit: Optional[str] = None  # required by the form whenever samplesizeValue is entered - anything from "handful" to "cm3"
    recordedBy: Optional[str] = None
    eventRemarks: Optional[str] = None
    datarestricted: Optional[str] = None  # "Y" or "N" - ticked as a checkbox on the form
    licenceHolder: Optional[str] = None   # required by the form whenever datarestricted == "Y"
    dataSource: Optional[str] = None      # free-text notes only - not a substitute for a real literature/project link (see sourceCategory below)

    # Source of record - what kind of source this sample came from, and
    # (for the two structured categories) a link to the specific
    # literature reference or project it came from. dataSource[free text]
    # itself is composed server-side from these, so the historic
    # free-text convention already in that column stays consistent for
    # new rows too.
    sourceCategory: Optional[str] = None  # e.g. "Personal collection", "Formal project or survey", "Published literature", "Museum or institutional collection", "Recording event", "Other"
    sourceLiteratureID: Optional[str] = None   # set when sourceCategory == "Published literature"
    sourceProjectID: Optional[int] = None      # set when sourceCategory == "Formal project or survey"
    sourceOtherDetail: Optional[str] = None    # free text for any category, e.g. which museum, or event name


class LiteratureSubmission(BaseModel):
    authorName: Optional[str] = None
    editorName: Optional[str] = None
    yearPublished: Optional[str] = None
    articleTitle: Optional[str] = None
    publicationTitle: Optional[str] = None
    publicationSeries: Optional[str] = None
    publicationVolume: Optional[str] = None
    publicationIssue: Optional[str] = None
    publicationTotalpages: Optional[str] = None
    publicationPages: Optional[str] = None
    publishedBy: Optional[str] = None
    publicationISBNorISSN: Optional[str] = None
    publicationDOI: Optional[str] = None
    sourceURL: Optional[str] = None
    litNotes: Optional[str] = None


class ProjectSubmission(BaseModel):
    project_name: str
    project_category: str  # "Survey or monitoring programme" | "Biological records centre bulk download"
    website_url: Optional[str] = None
    description: Optional[str] = None


class ObservationSubmission(BaseModel):
    eventID: str  # which sample this observation belongs to
    taxonID: str
    identifiedBy: Optional[str] = None
    identificationVerificationStatus: Optional[str] = None
    identificationRemarks: Optional[str] = None
    basisOfRecord: Optional[str] = None
    idTechnique: Optional[str] = None
    idText: Optional[str] = None

class ObservationSelfEditSubmission(BaseModel):
    taxonID: str
    identifiedBy: Optional[str] = None
    identificationVerificationStatus: Optional[str] = None
    identificationRemarks: Optional[str] = None
    basisOfRecord: Optional[str] = None
    idTechnique: Optional[str] = None
    idText: Optional[str] = None

class DemographicSubmission(BaseModel):
    observationID: str  # which observation this demographic group belongs to
    sex: Optional[str] = None            # dropdown: male / female / undetermined / mixed
    lifestage: Optional[str] = None      # dropdown: egg / prolarva / larva / protonymph / deutonymph / tritonymph / nymph / juvenile / adult / dead remains / undetermined / sign / gall
    count: Optional[str] = None          # stored as text in the DB, but entered as a number on the form
    density: Optional[str] = None
    densityUnit: Optional[str] = None
    minCount: Optional[str] = None
    maxCount: Optional[str] = None
    countDescription: Optional[str] = None


class SpecimenSubmission(BaseModel):
    demographicID: str  # which demographic group this specimen belongs to
    specCount: Optional[str] = None
    specLocation: Optional[str] = None
    specRef: Optional[str] = None
    specPreservation: Optional[str] = None
    specType: Optional[str] = None
    specComments: Optional[str] = None
    # specBarcode and specPhotos are deliberately NOT included here - both
    # are legacy double-precision columns from the original import (same
    # blank-column mistyping bug as elsewhere) and have been functionally
    # superseded: barcode data now belongs in specimen_barcodes, and
    # photos already go through observation_media (which links directly
    # to specimen_id). Wiring the form to the old columns would just
    # create a second, wrong place for this data to live.


class VerificationActionSubmission(BaseModel):
    action_type: str  # 'accepted' | 'rejected' | 'reassigned' | 'queried'
    notes: Optional[str] = None
    reassigned_taxon_id: Optional[str] = None  # required only when action_type == 'reassigned'


class TaxonomyEditSubmission(BaseModel):
    """
    Full-record edit for one taxon. Deliberately a full-replace shape
    (like the sample/observation submission forms) rather than a
    partial patch - the editor page always sends every editable
    field, whether or not the person actually changed it, which
    avoids any ambiguity between "field not sent" and "field
    deliberately cleared to blank".
    """
    scientificName: Optional[str] = None
    scientificnameAuthorship: Optional[str] = None
    taxonrank: Optional[str] = None
    taxonomicStatus: Optional[str] = None
    nomenclaturalStatus: Optional[str] = None
    taxonRemarks: Optional[str] = None
    parentNameUsageID: Optional[str] = None   # hierarchical parent - blank if this is a top-level taxon or a synonym
    acceptedNameUsageID: Optional[str] = None  # set this to mark the taxon as a synonym of another taxon
    notes: Optional[str] = None  # reason for the edit - stored in admin_activity_log, not on the taxon itself


class TaxonLiteratureLinkSubmission(BaseModel):
    """
    Links one literature reference to one taxon, via
    taxonomy_literature_junction, tagged with which of the five
    relationship types the public taxonomy page groups citations into
    (see get_taxon_literature) - including "Identification Key" as
    its own category, since a reference recording a taxonomic or
    synonymy decision (what's synonymised with what, which genus a
    species now sits in) is a different kind of thing from a
    reference that's usable to identify the taxon, and conflating the
    two under "Taxonomy or synonymy from" was misleading. There is no
    separate is_identification_key flag any more - it's derived
    server-side from Type == "Identification Key" - so the two can
    never disagree. key_scope_rank is still free-standing on this
    model: it's only meaningful when Type is "Identification Key",
    and records which rank the key covers (e.g. a species-level
    reference might actually be a key to the whole family).
    """
    litID: str
    Type: str  # one of VALID_TAXON_LITERATURE_TYPES below
    key_scope_rank: Optional[str] = None
    online_resource_url: Optional[str] = None
    access_notes: Optional[str] = None
    notes: Optional[str] = None  # reason, for the activity log


class TaxonomyCreateSubmission(BaseModel):
    scientificName: str
    scientificnameAuthorship: Optional[str] = None
    taxonrank: str
    taxonomicStatus: Optional[str] = "accepted"
    nomenclaturalStatus: Optional[str] = None
    taxonRemarks: Optional[str] = None
    parentNameUsageID: Optional[str] = None    # set this for a new taxon in the hierarchy
    acceptedNameUsageID: Optional[str] = None  # OR set this for a new synonym of an existing taxon (not both)
    literature_links: Optional[List[TaxonLiteratureLinkSubmission]] = None  # attach references at creation time
    notes: Optional[str] = None


# ----------------------------------------------------------------
# Record editor models (samples / observations / demographics /
# specimens) - all full-replace edit shapes, same convention as
# TaxonomyEditSubmission: the form always sends every editable
# field, so there's never ambiguity between "not sent" and
# "deliberately cleared".
# ----------------------------------------------------------------

class SampleEditSubmission(BaseModel):
    samplingLocation: Optional[str] = None
    decimalLatitude: Optional[str] = None   # stored as text in the DB, not numeric - kept as str so the diff never falsely flags an unchanged value
    decimalLongitude: Optional[str] = None  # same
    coordinateuncertaintyinmeters: Optional[str] = None
    bngx: Optional[str] = None
    bngy: Optional[str] = None
    gridRef: Optional[str] = None
    earliestDateCollected: Optional[str] = None
    latestDateCollected: Optional[str] = None
    habitat: Optional[str] = None
    microhabitat: Optional[str] = None
    SHADe: Optional[str] = None
    samplingProtocol: Optional[str] = None
    samplesizeValue: Optional[float] = None
    samplesizeUnit: Optional[str] = None
    recordedBy: Optional[str] = None
    eventRemarks: Optional[str] = None
    datarestricted: Optional[str] = None
    licenceHolder: Optional[str] = None
    dataSource: Optional[str] = None  # maps to "dataSource[free text]"
    notes: Optional[str] = None  # reason, for the activity log


class SampleDuplicateSubmission(BaseModel):
    notes: Optional[str] = None


class SampleLiteratureLinkSubmission(BaseModel):
    litID: str
    Type: Optional[str] = "source of record"
    notes: Optional[str] = None


class SampleProjectLinkSubmission(BaseModel):
    project_id: int
    type: Optional[str] = "source of record"
    notes: Optional[str] = None


class ObservationEditSubmission(BaseModel):
    eventID: Optional[str] = None  # which sample this belongs to - change to re-home it (e.g. after a microhabitat split)
    taxonID: Optional[str] = None
    identifiedBy: Optional[str] = None
    identificationVerificationStatus: Optional[str] = None
    identificationRemarks: Optional[str] = None
    collectionID: Optional[str] = None
    catalogNumber: Optional[str] = None
    basisOfRecord: Optional[str] = None
    idTechnique: Optional[str] = None
    litID: Optional[str] = None  # the single "primary reference" field already on observations
    idText: Optional[str] = None  # maps to "idText[free_text]"
    occurrenceRemarks: Optional[str] = None
    share_with_nbn: Optional[bool] = True
    share_with_gbif: Optional[bool] = True
    notes: Optional[str] = None  # reason, for the activity log
    # verification_status / verified_by / verified_date / verification_notes
    # are deliberately NOT editable here - they're managed through the
    # audited /review workflow (submit_verification_action) so every
    # change to them stays in observation_verification_actions.


class ObservationDuplicateSubmission(BaseModel):
    new_event_id: Optional[str] = None   # defaults to the same sample if omitted
    new_taxon_id: Optional[str] = None   # defaults to the same taxon if omitted
    copy_demographics: bool = False      # also deep-copy this observation's demographics (and their specimens)
    notes: Optional[str] = None


class ObservationLiteratureLinkSubmission(BaseModel):
    litID: str
    type: Optional[str] = "Identified using"  # one of VALID_OBSERVATION_LITERATURE_TYPES below
    notes: Optional[str] = None


class DemographicEditSubmission(BaseModel):
    sex: Optional[str] = None
    lifestage: Optional[str] = None
    count: Optional[str] = None
    density: Optional[str] = None
    densityUnit: Optional[str] = None
    minCount: Optional[str] = None
    maxCount: Optional[str] = None
    countDescription: Optional[str] = None
    notes: Optional[str] = None


class SpecimenEditSubmission(BaseModel):
    specCount: Optional[str] = None
    specLocation: Optional[str] = None
    specRef: Optional[str] = None
    specPreservation: Optional[str] = None
    specType: Optional[str] = None
    specComments: Optional[str] = None
    notes: Optional[str] = None


@app.post("/api/v1/submit/sample")
def submit_sample(payload: SampleSubmission, user: dict = Depends(require_contributor)):
    """
    Creates a new sample (sampling event) submitted via the website.
    Gets a WEB-prefixed eventID so it can never collide with
    historic imported data. Starts as belongs-to-this-user, pending
    review - observations can then be added to it one at a time via
    /api/v1/submit/observation, using the returned eventID.
    """
    if payload.samplesizeValue is not None and not (payload.samplesizeUnit and payload.samplesizeUnit.strip()):
        raise HTTPException(status_code=400, detail="samplesizeUnit is required whenever samplesizeValue is given")
    if payload.datarestricted == "Y" and not (payload.licenceHolder and payload.licenceHolder.strip()):
        raise HTTPException(status_code=400, detail="licenceHolder is required when datarestricted is 'Y'")

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT nextval('web_eventid_seq');")
        new_id = f"WEB-{cursor.fetchone()['nextval']}"

        # Compose the dataSource[free text] summary. Historic rows in
        # this column hold plain descriptive text (e.g. "A.N. Other
        # personal collection") - new rows follow the same
        # spirit, built from the structured category/link the
        # contributor picked, so the column stays readable at a glance
        # even though the real link now lives in a junction table.
        data_source_summary = payload.sourceCategory or None
        if payload.sourceCategory == "Published literature" and payload.sourceLiteratureID:
            cursor.execute("""
                SELECT CONCAT_WS(', ', "authorName", "yearPublished", "articleTitle") AS summary
                FROM literature WHERE "litID" = %s;
            """, (payload.sourceLiteratureID,))
            lit_row = cursor.fetchone()
            if lit_row and lit_row["summary"]:
                data_source_summary = f"Published literature: {lit_row['summary']}"
        elif payload.sourceCategory == "Formal project or survey" and payload.sourceProjectID:
            cursor.execute("SELECT project_name FROM recording_projects WHERE project_id = %s;", (payload.sourceProjectID,))
            proj_row = cursor.fetchone()
            if proj_row:
                data_source_summary = f"Formal project or survey: {proj_row['project_name']}"
        elif payload.sourceOtherDetail:
            data_source_summary = f"{payload.sourceCategory}: {payload.sourceOtherDetail}" if payload.sourceCategory else payload.sourceOtherDetail

        # The person's own free-text "Data source notes" are
        # deliberately supplementary, not a replacement - it's always
        # appended to the structured summary above, never overwrites
        # it, since the real traceable link (if any) is the
        # sourceCategory + literature/project junction row, not this text.
        if payload.dataSource and payload.dataSource.strip():
            data_source_summary = f"{data_source_summary} - {payload.dataSource.strip()}" if data_source_summary else payload.dataSource.strip()

        cursor.execute("""
            INSERT INTO samples (
                "eventID", "samplingLocation", "decimalLatitude", "decimalLongitude",
                "coordinateuncertaintyinmeters", "earliestDateCollected", "latestDateCollected",
                "habitat", "microhabitat", "SHADe", "samplingProtocol",
                "samplesizeValue", "samplesizeUnit", "recordedBy", "eventRemarks",
                "datarestricted", "licenceHolder", "dataSource[free text]",
                submitted_by_user_id, entered_by, entered_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP
            );
        """, (
            new_id, payload.samplingLocation, payload.decimalLatitude, payload.decimalLongitude,
            payload.coordinateUncertaintyInMeters, payload.earliestDateCollected, payload.latestDateCollected,
            payload.habitat, payload.microhabitat, payload.SHADe, payload.samplingProtocol,
            payload.samplesizeValue, payload.samplesizeUnit, payload.recordedBy, payload.eventRemarks,
            payload.datarestricted, payload.licenceHolder, data_source_summary,
            user["user_id"], user["display_name"]
        ))

        # Link to the specific literature reference or project, if one
        # was chosen - this is what actually makes the source
        # queryable/traceable later, not just descriptive text.
        if payload.sourceCategory == "Published literature" and payload.sourceLiteratureID:
            cursor.execute("""
                INSERT INTO sample_literature_junction ("eventID", "Type", "litID")
                VALUES (%s, %s, %s);
            """, (new_id, "source of record", payload.sourceLiteratureID))
        elif payload.sourceCategory == "Formal project or survey" and payload.sourceProjectID:
            cursor.execute("""
                INSERT INTO sample_project_junction ("eventID", project_id, type)
                VALUES (%s, %s, %s);
            """, (new_id, payload.sourceProjectID, "source of record"))

        # Build the spatial point immediately, if coordinates were given,
        # so this sample behaves identically to imported data on the map
        if payload.decimalLatitude is not None and payload.decimalLongitude is not None:
            cursor.execute("""
                UPDATE samples
                SET geom_wgs84 = ST_SetSRID(ST_MakePoint(%s, %s), 4326)
                WHERE "eventID" = %s;
            """, (payload.decimalLongitude, payload.decimalLatitude, new_id))

        conn.commit()
        return {"eventID": new_id, "message": "Sample created. Add observations to it using this eventID."}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Could not create sample: {str(e)}")
    finally:
        cursor.close()
        conn.close()


# ==========================================================
# BATCH UPLOAD (contributor - superusers additionally skip review)
# ==========================================================
# Lets a contributor download a multi-sheet Excel template, fill in
# a whole batch of new samples/observations (and optionally
# demographics/specimens) offline, and upload it back. New samples
# only - see the architecture notes for why. Whole-batch atomic: the
# entire upload succeeds together or nothing is written. A species
# name that doesn't exactly match anything in the taxonomy table
# never blocks the upload - the observation is still created with
# taxonID left NULL and the typed name preserved in
# proposed_taxon_name, for a superuser to resolve later via the
# Review Queue, using the taxonomy editor's existing tools.

BATCH_MAX_TEMPLATE_ROWS = 500  # generous fixed size for dropdown source ranges - simple and robust at single-batch scale

BATCH_SAMPLE_HEADERS = [
    "Sample Ref*", "samplingLocation", "decimalLatitude", "decimalLongitude",
    "coordinateUncertaintyInMeters", "earliestDateCollected", "latestDateCollected",
    "habitat", "microhabitat", "SHADe", "samplingProtocol", "recordedBy", "eventRemarks"
]
BATCH_SOURCE_TYPES = {
    "Published literature",
    "Formal project or survey",
    "Museum or institutional collection",
    "Recording event",
    "Personal collection",
    "Other",
}

BATCH_OBSERVATION_HEADERS = [
    "Observation Ref*", "Sample Ref*", "Species*", "Species found?",
    "identifiedBy", "identificationVerificationStatus", "identificationRemarks",
    "basisOfRecord", "idTechnique", "idText"
]
BATCH_DEMOGRAPHIC_HEADERS = [
    "Demographic Ref*", "Observation Ref*", "sex", "lifestage", "count",
    "density", "densityUnit", "minCount", "maxCount", "countDescription"
]
BATCH_SPECIMEN_HEADERS = [
    "Demographic Ref*", "specCount", "specLocation", "specRef",
    "specPreservation", "specType", "specComments"
]
BATCH_SEX_OPTIONS = ["male", "female", "undetermined", "mixed"]
BATCH_LIFESTAGE_OPTIONS = [
    "egg", "prolarva", "larva", "protonymph", "deutonymph", "tritonymph",
    "nymph", "juvenile", "adult", "dead remains", "undetermined", "sign", "gall"
]

_BATCH_HEADER_FILL = PatternFill(start_color="1B4332", end_color="1B4332", fill_type="solid")
_BATCH_HEADER_FONT = Font(color="FFFFFF", bold=True)
_BATCH_REQUIRED_FONT = Font(color="FFFFFF", bold=True, italic=True)


def _batch_style_header_row(ws, headers):
    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.fill = _BATCH_HEADER_FILL
        cell.font = _BATCH_REQUIRED_FONT if header.endswith("*") else _BATCH_HEADER_FONT
    ws.freeze_panes = "A2"
    for col_idx, header in enumerate(headers, start=1):
        ws.column_dimensions[get_column_letter(col_idx)].width = max(14, min(32, len(header) + 4))


def _batch_add_table(ws, headers, table_name):
    last_col = get_column_letter(len(headers))
    ref = f"A1:{last_col}{BATCH_MAX_TEMPLATE_ROWS + 1}"
    table = Table(displayName=table_name, ref=ref)
    table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
    ws.add_table(table)


def _batch_add_dropdown(ws, col_letter, source_formula, first_row=2, last_row=None):
    last_row = last_row or (BATCH_MAX_TEMPLATE_ROWS + 1)
    dv = DataValidation(type="list", formula1=source_formula, allow_blank=True, showDropDown=False)
    dv.error = "Please choose a value from the dropdown list."
    dv.errorTitle = "Invalid entry"
    ws.add_data_validation(dv)
    dv.add(f"{col_letter}{first_row}:{col_letter}{last_row}")


def _build_batch_template(include_demographics: bool, include_specimens: bool, taxa: list, source: dict):
    """
    Builds the downloadable multi-sheet workbook. taxa is a list of
    dicts (taxon_id, scientific_name, authorship, rank, status) for
    the read-only Taxon Lookup reference sheet. source is
    {"source_type", "source_lit_id", "source_project_id",
    "source_other_detail", "source_display"} - fixed for the entire
    batch and written into a locked "Upload Source" sheet, since with
    batches running to hundreds of samples, linking each one
    individually afterwards would be impractical. Every sample this
    template produces gets exactly this one source.
    """
    include_specimens = include_specimens and include_demographics  # specimens need demographics to attach to

    wb = Workbook()
    wb.remove(wb.active)

    ws_instr = wb.create_sheet("Instructions")
    ws_instr.column_dimensions["A"].width = 100
    instructions = [
        "Aphanologia batch upload template",
        "",
        f"This template is locked to one source: {source['source_display']}. Every sample you add here will be linked to it - see the 'Upload Source' sheet.",
        "",
        "1. Fill in the Samples sheet first - one row per sampling event. Give each one a short, unique 'Sample Ref' (e.g. 'Site A visit 1') - this is just for linking rows within this file, it is not stored in the database.",
        "2. Fill in the Observations sheet - one row per species record. Pick the Sample Ref from the dropdown. Type the species name as accurately as you can; the 'Species found?' column will tell you if it matches something already in the database.",
    ]
    if include_demographics:
        instructions.append("3. If you have demographic detail (sex/lifestage/counts), fill in the Demographics sheet, picking the Observation Ref from the dropdown.")
    if include_specimens:
        instructions.append("4. If you have individual specimen records, fill in the Specimens sheet, picking the Demographic Ref from the dropdown.")
    instructions += [
        "5. Species names that don't match anything in the Taxon Lookup sheet are NOT rejected - they'll be queued for a superuser to review as a possible new record, once you upload.",
        "6. Save the file and upload it on the Batch Upload page. You'll see a validation report before anything is saved to the database.",
        "7. The whole upload succeeds or fails together - if any row has a structural problem (e.g. a Sample Ref that doesn't match anything on the Samples sheet), fix it and re-upload; nothing partial gets saved.",
        "8. Need a different source? Download a fresh template for it rather than editing the Upload Source sheet - it's locked, and mixing sources in one file isn't supported.",
    ]
    for i, line in enumerate(instructions, start=1):
        ws_instr.cell(row=i, column=1, value=line)
    ws_instr["A1"].font = Font(bold=True, size=14)

    ws_source = wb.create_sheet("Upload Source")
    ws_source.column_dimensions["A"].width = 22
    ws_source.column_dimensions["B"].width = 70
    source_rows = [
        ("Source Type", source["source_type"]),
        ("Literature ID", source.get("source_lit_id") or ""),
        ("Project ID", source.get("source_project_id") or ""),
        ("Other Detail", source.get("source_other_detail") or ""),
        ("Description", source["source_display"]),
    ]
    for i, (label, value) in enumerate(source_rows, start=1):
        label_cell = ws_source.cell(row=i, column=1, value=label)
        label_cell.font = Font(bold=True, color="1B4332")
        ws_source.cell(row=i, column=2, value=value)
    ws_source.cell(row=7, column=1, value="This sheet is locked - every sample in this file is linked to the source above. Download a separate template for a different source.").font = Font(italic=True, color="6C757D")
    ws_source.protection.sheet = True  # every cell defaults to locked; no cells are unlocked, so the whole sheet is read-only

    ws_samples = wb.create_sheet("Samples")
    _batch_style_header_row(ws_samples, BATCH_SAMPLE_HEADERS)
    _batch_add_table(ws_samples, BATCH_SAMPLE_HEADERS, "SamplesTable")

    ws_obs = wb.create_sheet("Observations")
    _batch_style_header_row(ws_obs, BATCH_OBSERVATION_HEADERS)
    _batch_add_table(ws_obs, BATCH_OBSERVATION_HEADERS, "ObservationsTable")
    _batch_add_dropdown(ws_obs, "B", f"=Samples!$A$2:$A${BATCH_MAX_TEMPLATE_ROWS + 1}")
    for row in range(2, BATCH_MAX_TEMPLATE_ROWS + 2):
        ws_obs.cell(
            row=row, column=4,
            value=f'=IFERROR(IF(C{row}="","",IF(COUNTIF(\'Taxon Lookup\'!$B:$B,C{row})>0,"found","not found - will be queued for review")),"")'
        )
    ws_obs["C1"].comment = Comment(
        "See the 'Taxon Lookup' sheet for names already in the database. If your species isn't there, type it anyway - it'll be queued for review rather than rejected.",
        "Aphanologia"
    )

    if include_demographics:
        ws_demo = wb.create_sheet("Demographics")
        _batch_style_header_row(ws_demo, BATCH_DEMOGRAPHIC_HEADERS)
        _batch_add_table(ws_demo, BATCH_DEMOGRAPHIC_HEADERS, "DemographicsTable")
        _batch_add_dropdown(ws_demo, "B", f"=Observations!$A$2:$A${BATCH_MAX_TEMPLATE_ROWS + 1}")
        _batch_add_dropdown(ws_demo, "C", '"' + ",".join(BATCH_SEX_OPTIONS) + '"')
        _batch_add_dropdown(ws_demo, "D", '"' + ",".join(BATCH_LIFESTAGE_OPTIONS) + '"')

    if include_specimens:
        ws_spec = wb.create_sheet("Specimens")
        _batch_style_header_row(ws_spec, BATCH_SPECIMEN_HEADERS)
        _batch_add_table(ws_spec, BATCH_SPECIMEN_HEADERS, "SpecimensTable")
        _batch_add_dropdown(ws_spec, "A", f"=Demographics!$A$2:$A${BATCH_MAX_TEMPLATE_ROWS + 1}")

    ws_lookup = wb.create_sheet("Taxon Lookup")
    lookup_headers = ["taxonID", "scientificName", "authorship", "rank", "status"]
    _batch_style_header_row(ws_lookup, lookup_headers)
    for i, t in enumerate(taxa, start=2):
        ws_lookup.cell(row=i, column=1, value=t.get("taxon_id"))
        ws_lookup.cell(row=i, column=2, value=t.get("scientific_name"))
        ws_lookup.cell(row=i, column=3, value=t.get("authorship"))
        ws_lookup.cell(row=i, column=4, value=t.get("rank"))
        ws_lookup.cell(row=i, column=5, value=t.get("status"))
    ws_lookup.freeze_panes = "A2"

    wb.active = wb["Instructions"]
    return wb


def _batch_cell_str(value):
    """
    Safely coerces an Excel cell value to a stripped string. Openpyxl
    returns numeric cells as int/float, not str - a plain
    (value or "").strip() blows up with an unhandled AttributeError
    the moment a Sample/Observation/Demographic Ref or a Species name
    is typed as a bare number (e.g. "1"), and because it's unhandled,
    FastAPI returns a plain-text 500 page rather than JSON, which then
    fails to parse in the browser ("Unexpected token 'I'..." from
    "Internal Server Error"). None becomes "" ; anything else becomes
    str(value) ; only then is it stripped.
    """
    return str(value).strip() if value is not None else ""


def _batch_sheet_to_rows(ws):
    """
    Reads a header-row sheet into a list of dicts keyed by header
    text, stopping cleanly at blank rows. Columns whose header ends
    in '?' are treated as computed helper columns (e.g. "Species
    found?") and ignored when deciding whether a row is genuinely
    blank, since those recompute to an empty string even when every
    real field on that row is untouched.
    """
    header_row = next(ws.iter_rows(min_row=1, max_row=1))
    headers = [c.value for c in header_row]
    rows = []
    for row in ws.iter_rows(min_row=2):
        values = {headers[i]: cell.value for i, cell in enumerate(row) if i < len(headers) and headers[i]}
        real_values = {k: v for k, v in values.items() if not str(k).endswith('?')}
        if all(v is None or str(v).strip() == '' for v in real_values.values()):
            continue
        rows.append({"_row": row[0].row, **values})
    return rows


def _batch_parse_workbook(file_bytes: bytes):
    """
    Loads the uploaded workbook and returns (samples, observations,
    demographics, specimens, source, parse_errors). demographics/
    specimens are empty lists if those sheets aren't present (a
    2-sheet upload). source is the fixed batch-wide sample source
    read back from the locked "Upload Source" sheet. parse_errors is
    non-empty only for structural workbook problems (missing required
    sheets, or a missing/invalid source) that make further validation
    meaningless.
    """
    parse_errors = []
    try:
        wb = load_workbook(io.BytesIO(file_bytes), data_only=False)
    except Exception as e:
        return [], [], [], [], {}, [f"Could not read this file as an Excel workbook: {str(e)}"]

    if "Samples" not in wb.sheetnames:
        parse_errors.append("Missing required 'Samples' sheet.")
    if "Observations" not in wb.sheetnames:
        parse_errors.append("Missing required 'Observations' sheet.")
    if "Upload Source" not in wb.sheetnames:
        parse_errors.append("Missing required 'Upload Source' sheet - this file wasn't generated by the Batch Upload template, or that sheet has been deleted.")
    if parse_errors:
        return [], [], [], [], {}, parse_errors

    ws_source = wb["Upload Source"]
    source = {
        "source_type": (ws_source["B1"].value or "").strip() if ws_source["B1"].value else None,
        "source_lit_id": (ws_source["B2"].value or "").strip() if ws_source["B2"].value else None,
        "source_project_id": (ws_source["B3"].value or "").strip() if ws_source["B3"].value else None,
        "source_other_detail": (ws_source["B4"].value or "").strip() if ws_source["B4"].value else None,
    }
    if not source["source_type"] or source["source_type"] not in BATCH_SOURCE_TYPES:
        parse_errors.append("The 'Upload Source' sheet is missing or has an invalid Source Type - please download a fresh template rather than editing this sheet.")
        return [], [], [], [], {}, parse_errors

    samples = _batch_sheet_to_rows(wb["Samples"])
    observations = _batch_sheet_to_rows(wb["Observations"])
    demographics = _batch_sheet_to_rows(wb["Demographics"]) if "Demographics" in wb.sheetnames else []
    specimens = _batch_sheet_to_rows(wb["Specimens"]) if "Specimens" in wb.sheetnames else []
    return samples, observations, demographics, specimens, source, []


def _batch_validate(samples, observations, demographics, specimens):
    """
    Runs Pass 1 (structural) and Pass 2 (cross-sheet referential
    integrity). Never fails on an unmatched taxon name - that's Pass
    3, handled separately in _batch_resolve_taxa since it needs a
    database connection and never produces a blocking error anyway.
    Returns (errors, warnings) - both lists of {"sheet", "row",
    "message"} dicts. Any entry in errors blocks commit; warnings
    (e.g. "these species names will be queued for review") don't.
    """
    errors = []

    sample_refs = {}
    for s in samples:
        ref = _batch_cell_str(s.get("Sample Ref*"))
        if not ref:
            errors.append({"sheet": "Samples", "row": s["_row"], "message": "Sample Ref is required."})
            continue
        if ref in sample_refs:
            errors.append({"sheet": "Samples", "row": s["_row"], "message": f"Duplicate Sample Ref '{ref}' (also used on row {sample_refs[ref]})."})
            continue
        sample_refs[ref] = s["_row"]

    if not samples:
        errors.append({"sheet": "Samples", "row": None, "message": "No sample rows found - the Samples sheet is empty."})

    observation_refs = {}
    for o in observations:
        obs_ref = _batch_cell_str(o.get("Observation Ref*"))
        sample_ref = _batch_cell_str(o.get("Sample Ref*"))
        species = _batch_cell_str(o.get("Species*"))
        if not obs_ref:
            errors.append({"sheet": "Observations", "row": o["_row"], "message": "Observation Ref is required."})
        elif obs_ref in observation_refs:
            errors.append({"sheet": "Observations", "row": o["_row"], "message": f"Duplicate Observation Ref '{obs_ref}' (also used on row {observation_refs[obs_ref]})."})
        else:
            observation_refs[obs_ref] = o["_row"]
        if not sample_ref:
            errors.append({"sheet": "Observations", "row": o["_row"], "message": "Sample Ref is required."})
        elif sample_ref not in sample_refs:
            errors.append({"sheet": "Observations", "row": o["_row"], "message": f"Sample Ref '{sample_ref}' does not match any row on the Samples sheet."})
        if not species:
            errors.append({"sheet": "Observations", "row": o["_row"], "message": "Species is required."})

    if not observations:
        errors.append({"sheet": "Observations", "row": None, "message": "No observation rows found - the Observations sheet is empty."})

    demographic_refs = {}
    for d in demographics:
        demo_ref = _batch_cell_str(d.get("Demographic Ref*"))
        obs_ref = _batch_cell_str(d.get("Observation Ref*"))
        if not demo_ref:
            errors.append({"sheet": "Demographics", "row": d["_row"], "message": "Demographic Ref is required."})
        elif demo_ref in demographic_refs:
            errors.append({"sheet": "Demographics", "row": d["_row"], "message": f"Duplicate Demographic Ref '{demo_ref}' (also used on row {demographic_refs[demo_ref]})."})
        else:
            demographic_refs[demo_ref] = d["_row"]
        if not obs_ref:
            errors.append({"sheet": "Demographics", "row": d["_row"], "message": "Observation Ref is required."})
        elif obs_ref not in observation_refs:
            errors.append({"sheet": "Demographics", "row": d["_row"], "message": f"Observation Ref '{obs_ref}' does not match any row on the Observations sheet."})

    for sp in specimens:
        demo_ref = _batch_cell_str(sp.get("Demographic Ref*"))
        if not demo_ref:
            errors.append({"sheet": "Specimens", "row": sp["_row"], "message": "Demographic Ref is required."})
        elif demo_ref not in demographic_refs:
            errors.append({"sheet": "Specimens", "row": sp["_row"], "message": f"Demographic Ref '{demo_ref}' does not match any row on the Demographics sheet."})

    return errors


def _batch_resolve_taxa(cursor, observations):
    """
    Pass 3: exact (case-insensitive) match of each Species name
    against taxonomy.scientificName. Returns a dict of
    row_number -> {"taxon_id": ... } or {"proposed_name": ...} -
    never an error; an unmatched name is always resolvable, just not
    to an existing taxonID yet.
    """
    resolution = {}
    unmatched_names = set()
    for o in observations:
        species = _batch_cell_str(o.get("Species*"))
        if not species:
            continue
        cursor.execute('SELECT "taxonID" FROM taxonomy WHERE LOWER("scientificName") = LOWER(%s) LIMIT 1;', (species,))
        row = cursor.fetchone()
        if row:
            resolution[o["_row"]] = {"taxon_id": row["taxonID"], "proposed_name": None}
        else:
            resolution[o["_row"]] = {"taxon_id": None, "proposed_name": species}
            unmatched_names.add(species)
    return resolution, sorted(unmatched_names)


def _batch_resolve_source(cursor, source: dict):
    """
    Re-verifies the source embedded in the workbook at commit/validate
    time rather than trusting it blindly - a template could have been
    downloaded weeks before being uploaded, and the literature entry
    or project it pointed at could have been deleted or edited since.
    Returns (display_text, error_message) - exactly one is set.
    """
    source_type = source.get("source_type")
    if source_type == "Published literature":
        cursor.execute("""
            SELECT CONCAT_WS(', ', "authorName", "yearPublished", "articleTitle", "publicationTitle") AS ref
            FROM literature WHERE "litID" = %s;
        """, (source.get("source_lit_id"),))
        row = cursor.fetchone()
        if not row:
            return None, f"The literature reference this template was linked to (litID {source.get('source_lit_id')}) no longer exists - download a fresh template."
        return f"Published literature: {row['ref']}", None
    elif source_type == "Formal project or survey":
        cursor.execute("SELECT project_name FROM recording_projects WHERE project_id = %s;", (source.get("source_project_id"),))
        row = cursor.fetchone()
        if not row:
            return None, f"The project this template was linked to (id {source.get('source_project_id')}) no longer exists - download a fresh template."
        return f"Formal project or survey: {row['project_name']}", None
    elif source_type in BATCH_SOURCE_TYPES:
        detail = source.get("source_other_detail")
        return f"{source_type}{': ' + detail if detail else ''}", None
    else:
        return None, "Missing or invalid source information in the 'Upload Source' sheet - download a fresh template."


@app.get("/api/v1/batch/template")
def download_batch_template(
    source_type: str = Query(..., description="One of: " + ", ".join(sorted(BATCH_SOURCE_TYPES))),
    source_lit_id: Optional[str] = Query(None, description="Required when source_type is 'Published literature'"),
    source_project_id: Optional[int] = Query(None, description="Required when source_type is 'Formal project or survey'"),
    source_other_detail: Optional[str] = Query(None, description="Required for Museum, Recording event, and Other; optional for Personal collection"),
    include_demographics: bool = Query(True),
    include_specimens: bool = Query(True),
    valid_taxa_only: bool = Query(True),
    user: dict = Depends(require_contributor)
):
    """
    Generates and streams a multi-sheet .xlsx template, sized to
    whichever levels of detail the contributor wants to include.
    valid_taxa_only controls what shows on the in-workbook Taxon
    Lookup reference sheet only - it does not restrict what can
    actually be typed into the Species column (see _batch_resolve_taxa).

    Every sample this template produces is linked to exactly one
    source - required here, not per-row, because linking each sample
    individually after the fact doesn't scale once a batch runs to
    hundreds of rows. The resolved source is embedded in a locked
    sheet in the workbook and applied to every sample at commit time.
    """
    if source_type not in BATCH_SOURCE_TYPES:
        raise HTTPException(status_code=400, detail=f"source_type must be one of {sorted(BATCH_SOURCE_TYPES)}")

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if valid_taxa_only:
            cursor.execute("""
                SELECT "taxonID" AS taxon_id, "scientificName" AS scientific_name,
                       "scientificnameAuthorship" AS authorship, "taxonrank" AS rank, "taxonomicStatus" AS status
                FROM taxonomy WHERE "taxonomicStatus" = 'accepted' ORDER BY "scientificName";
            """)
        else:
            cursor.execute("""
                SELECT "taxonID" AS taxon_id, "scientificName" AS scientific_name,
                       "scientificnameAuthorship" AS authorship, "taxonrank" AS rank, "taxonomicStatus" AS status
                FROM taxonomy ORDER BY "scientificName";
            """)
        taxa = cursor.fetchall()

        source = {"source_type": source_type, "source_lit_id": None, "source_project_id": None, "source_other_detail": None}
        if source_type == "Published literature":
            if not source_lit_id:
                raise HTTPException(status_code=400, detail="source_lit_id is required when source_type is 'Published literature'")
            cursor.execute("""
                SELECT CONCAT_WS(', ', "authorName", "yearPublished", "articleTitle", "publicationTitle") AS ref
                FROM literature WHERE "litID" = %s;
            """, (source_lit_id,))
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=400, detail=f"No literature entry found with litID {source_lit_id}")
            source["source_lit_id"] = source_lit_id
            source["source_display"] = f"Published literature: {row['ref']}"
        elif source_type == "Formal project or survey":
            if not source_project_id:
                raise HTTPException(status_code=400, detail="source_project_id is required when source_type is 'Formal project or survey'")
            cursor.execute("SELECT project_name FROM recording_projects WHERE project_id = %s;", (source_project_id,))
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=400, detail=f"No project found with id {source_project_id}")
            source["source_project_id"] = str(source_project_id)
            source["source_display"] = f"Formal project or survey: {row['project_name']}"
        elif source_type == "Personal collection":
            source["source_other_detail"] = source_other_detail
            source["source_display"] = f"Personal collection{': ' + source_other_detail if source_other_detail else ''}"
        else:  # Museum or institutional collection / Recording event / Other
            if not source_other_detail or not source_other_detail.strip():
                raise HTTPException(status_code=400, detail=f"source_other_detail is required when source_type is '{source_type}'")
            source["source_other_detail"] = source_other_detail
            source["source_display"] = f"{source_type}: {source_other_detail}"
    finally:
        cursor.close()
        conn.close()

    wb = _build_batch_template(include_demographics, include_specimens, taxa, source)
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=aphanologia_batch_template.xlsx"}
    )


@app.post("/api/v1/batch/validate")
async def validate_batch_upload(file: UploadFile = File(...), user: dict = Depends(require_contributor)):
    """
    Parses and fully validates an uploaded workbook WITHOUT writing
    anything to the database. Returns every structural/referential
    problem found (Pass 1 + Pass 2), plus a non-blocking list of
    species names that will be queued for superuser review (Pass 3
    never blocks). The commit endpoint re-runs this exact same
    validation before writing anything, so a stale validate result
    can never lead to a bad commit.
    """
    file_bytes = await file.read()
    samples, observations, demographics, specimens, source, parse_errors = _batch_parse_workbook(file_bytes)
    if parse_errors:
        return {"can_commit": False, "errors": [{"sheet": None, "row": None, "message": m} for m in parse_errors], "unmatched_taxa": [], "source": None}

    errors = _batch_validate(samples, observations, demographics, specimens)

    unmatched_taxa = []
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        source_display, source_error = _batch_resolve_source(cursor, source)
        if source_error:
            errors.append({"sheet": "Upload Source", "row": None, "message": source_error})
        if not any(e["sheet"] == "Observations" and e["row"] is None for e in errors):
            _, unmatched_taxa = _batch_resolve_taxa(cursor, observations)
    finally:
        cursor.close()
        conn.close()

    return {
        "can_commit": len(errors) == 0,
        "errors": errors,
        "unmatched_taxa": unmatched_taxa,
        "source": source_display,
        "counts": {
            "samples": len(samples),
            "observations": len(observations),
            "demographics": len(demographics),
            "specimens": len(specimens)
        }
    }


@app.post("/api/v1/batch/commit")
async def commit_batch_upload(file: UploadFile = File(...), user: dict = Depends(require_contributor)):
    """
    Re-validates, then - only if that validation is completely clean
    of Pass 1/Pass 2 errors - writes every sample, observation,
    demographic, and specimen in one transaction. Every sample gets
    linked to the one source embedded in the workbook (see
    _batch_resolve_source) via the same sample_literature_junction/
    sample_project_junction tables the admin tools use, so a
    135-sample batch never needs linking one row at a time afterwards.
    An unmatched species name never blocks this; that observation is
    created with taxonID NULL and proposed_taxon_name set instead,
    ready for superuser review. Superusers/hyperusers get every
    observation auto-accepted (verification_status = 'verified', with
    a matching row logged in observation_verification_actions so the
    audit trail still shows how it was verified) - contributors'
    uploads go to the same pending review queue as a single manual
    submission.
    """
    file_bytes = await file.read()
    samples, observations, demographics, specimens, source, parse_errors = _batch_parse_workbook(file_bytes)
    if parse_errors:
        raise HTTPException(status_code=400, detail="; ".join(parse_errors))

    errors = _batch_validate(samples, observations, demographics, specimens)
    if errors:
        raise HTTPException(status_code=400, detail=f"{len(errors)} row(s) failed validation - re-run /api/v1/batch/validate for details before committing.")

    is_superuser = user["role"] in ("superuser", "hyperuser")

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        source_display, source_error = _batch_resolve_source(cursor, source)
        if source_error:
            raise HTTPException(status_code=400, detail=source_error)

        taxon_resolution, unmatched_taxa = _batch_resolve_taxa(cursor, observations)

        # --- Samples ---
        sample_ref_to_event_id = {}
        for s in samples:
            cursor.execute("SELECT nextval('web_eventid_seq');")
            new_event_id = f"WEB-{cursor.fetchone()['nextval']}"
            sample_ref_to_event_id[_batch_cell_str(s.get("Sample Ref*"))] = new_event_id

            # Only "Museum/institutional collection", "Recording event",
            # "Personal collection" and "Other" have no dedicated DB
            # entity to link to - those go in dataSource[free text].
            # Literature and Project sources get a real linked row in
            # their junction table instead (see below), same as a
            # single manual sample submission would.
            free_text_source = source_display if source["source_type"] not in ("Published literature", "Formal project or survey") else None

            cursor.execute("""
                INSERT INTO samples (
                    "eventID", "samplingLocation", "decimalLatitude", "decimalLongitude",
                    "coordinateuncertaintyinmeters", "earliestDateCollected", "latestDateCollected",
                    "habitat", "microhabitat", "SHADe", "samplingProtocol", "recordedBy", "eventRemarks",
                    "dataSource[free text]", submitted_by_user_id, entered_by, entered_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP
                );
            """, (
                new_event_id, s.get("samplingLocation"), s.get("decimalLatitude"), s.get("decimalLongitude"),
                s.get("coordinateUncertaintyInMeters"), s.get("earliestDateCollected"), s.get("latestDateCollected"),
                s.get("habitat"), s.get("microhabitat"), s.get("SHADe"), s.get("samplingProtocol"),
                s.get("recordedBy"), s.get("eventRemarks"), free_text_source,
                user["user_id"], user["display_name"]
            ))
            if s.get("decimalLatitude") is not None and s.get("decimalLongitude") is not None:
                cursor.execute("""
                    UPDATE samples SET geom_wgs84 = ST_SetSRID(ST_MakePoint(%s::float8, %s::float8), 4326)
                    WHERE "eventID" = %s;
                """, (s["decimalLongitude"], s["decimalLatitude"], new_event_id))

            if source["source_type"] == "Published literature":
                cursor.execute("""
                    INSERT INTO sample_literature_junction ("eventID", "Type", "litID") VALUES (%s, %s, %s);
                """, (new_event_id, "source of record", source["source_lit_id"]))
            elif source["source_type"] == "Formal project or survey":
                cursor.execute("""
                    INSERT INTO sample_project_junction ("eventID", project_id, type) VALUES (%s, %s, %s);
                """, (new_event_id, int(source["source_project_id"]), "source of record"))

        # --- Observations ---
        observation_ref_to_id = {}
        verification_status = "verified" if is_superuser else "pending"
        for o in observations:
            cursor.execute("SELECT nextval('web_observationid_seq');")
            new_obs_id = f"WEB-{cursor.fetchone()['nextval']}"
            observation_ref_to_id[_batch_cell_str(o.get("Observation Ref*"))] = new_obs_id

            event_id = sample_ref_to_event_id[_batch_cell_str(o.get("Sample Ref*"))]
            resolved = taxon_resolution.get(o["_row"], {"taxon_id": None, "proposed_name": None})

            cursor.execute("""
                INSERT INTO observations (
                    "observationID", "eventID", "taxonID", proposed_taxon_name, "identifiedBy",
                    "identificationVerificationStatus", "identificationRemarks",
                    "basisOfRecord", "idTechnique", "idText[free_text]",
                    verification_status, verified_by, verified_date,
                    submitted_by_user_id, entered_by, entered_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP
                );
            """, (
                new_obs_id, event_id, resolved["taxon_id"], resolved["proposed_name"], o.get("identifiedBy"),
                o.get("identificationVerificationStatus"), o.get("identificationRemarks"),
                o.get("basisOfRecord"), o.get("idTechnique"), o.get("idText"),
                verification_status, (user["display_name"] if is_superuser else None), None,
                user["user_id"], user["display_name"]
            ))
            # verified_date needs CURRENT_TIMESTAMP, which can't be a
            # bound parameter alongside the rest of this row - set
            # separately, only for superuser auto-verified rows.
            if is_superuser:
                cursor.execute("""
                    UPDATE observations SET verified_date = CURRENT_TIMESTAMP WHERE "observationID" = %s;
                """, (new_obs_id,))
                cursor.execute("""
                    INSERT INTO observation_verification_actions (
                        "observationID", action_type, notes, performed_by_user_id
                    ) VALUES (%s, 'accepted', 'Auto-accepted: superuser batch upload', %s);
                """, (new_obs_id, user["user_id"]))

        # --- Demographics ---
        demographic_ref_to_id = {}
        for d in demographics:
            cursor.execute("SELECT nextval('web_demographicid_seq');")
            new_demo_id = f"WEB-{cursor.fetchone()['nextval']}"
            demographic_ref_to_id[_batch_cell_str(d.get("Demographic Ref*"))] = new_demo_id
            obs_id = observation_ref_to_id[_batch_cell_str(d.get("Observation Ref*"))]

            cursor.execute("""
                INSERT INTO observation_demographics (
                    "demographicID", "observationID", sex, lifestage, count,
                    density, "densityUnit", "minCount", "maxCount", "countDescription"
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
            """, (
                new_demo_id, obs_id, d.get("sex"), d.get("lifestage"), d.get("count"),
                d.get("density"), d.get("densityUnit"), d.get("minCount"), d.get("maxCount"), d.get("countDescription")
            ))

        # --- Specimens ---
        for sp in specimens:
            cursor.execute("SELECT nextval('web_specimenid_seq');")
            new_spec_id = f"WEB-{cursor.fetchone()['nextval']}"
            demo_id = demographic_ref_to_id[_batch_cell_str(sp.get("Demographic Ref*"))]

            cursor.execute("""
                INSERT INTO specimens (
                    "specimenID", "demographicID", "specCount", "specLocation",
                    "specRef", "specPreservation", "specType", "specComments"
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
            """, (
                new_spec_id, demo_id, sp.get("specCount"), sp.get("specLocation"),
                sp.get("specRef"), sp.get("specPreservation"), sp.get("specType"), sp.get("specComments")
            ))

        conn.commit()
        return {
            "message": "Batch upload committed.",
            "source": source_display,
            "samples_created": len(sample_ref_to_event_id),
            "observations_created": len(observation_ref_to_id),
            "demographics_created": len(demographic_ref_to_id),
            "specimens_created": len(specimens),
            "auto_verified": is_superuser,
            "queued_for_taxonomy_review": unmatched_taxa,
            "sample_ref_map": sample_ref_to_event_id,
            "observation_ref_map": observation_ref_to_id
        }
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Could not commit batch upload: {str(e)}")
    finally:
        cursor.close()
        conn.close()


# ==========================================================
# LITERATURE & PROJECT LOOKUP (source-of-record picker)
# ==========================================================

@app.get("/api/v1/literature/search")
def search_literature(
    q: str = Query(..., min_length=2, description="Fuzzy search across author, title, year, publication"),
    limit: int = Query(15, ge=1, le=50)
):
    """
    Fuzzy (typo-tolerant) search across literature entries, for the
    "choose a reference" picker on the sample submission form. Matches
    on a combination of author, article title, year, and publication
    title - ranked by trigram similarity, with an exact-substring match
    boosted to the top since that's usually what a contributor is
    actually looking for.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT
                "litID" AS lit_id,
                CONCAT_WS(', ', "authorName", "yearPublished", "articleTitle", "publicationTitle") AS formatted_ref,
                "sourceURL" AS url,
                similarity(search_text, %s) AS sim
            FROM literature
            WHERE search_text %% %s OR search_text ILIKE %s
            ORDER BY
                CASE WHEN search_text ILIKE %s THEN 0 ELSE 1 END,
                sim DESC
            LIMIT %s;
        """, (q, q, f"%{q}%", f"%{q}%", limit))
        rows = cursor.fetchall()
        return {"query": q, "count": len(rows), "results": rows}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query error: {str(e)}")
    finally:
        cursor.close()
        conn.close()


@app.post("/api/v1/literature")
def create_literature(payload: LiteratureSubmission, user: dict = Depends(require_contributor)):
    """
    Adds a new literature entry - used when a contributor needs to
    cite a reference as their sample's source of record, and it isn't
    already catalogued. Gets a WEB-prefixed litID, same convention as
    every other web-submitted ID in this project.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT nextval('web_litid_seq');")
        new_id = f"WEB-{cursor.fetchone()['nextval']}"

        cursor.execute("""
            INSERT INTO literature (
                "litID", "authorName", "editorName", "yearPublished", "articleTitle",
                "publicationTitle", "publicationSeries", "publicationVolume", "publicationIssue",
                "publicationTotalpages", "publicationPages", "publishedBy",
                "publicationISBNorISSN", "publicationDOI", "sourceURL", "litNotes"
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            );
        """, (
            new_id, payload.authorName, payload.editorName, payload.yearPublished, payload.articleTitle,
            payload.publicationTitle, payload.publicationSeries, payload.publicationVolume, payload.publicationIssue,
            payload.publicationTotalpages, payload.publicationPages, payload.publishedBy,
            payload.publicationISBNorISSN, payload.publicationDOI, payload.sourceURL, payload.litNotes
        ))
        conn.commit()
        return {"litID": new_id}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Could not create literature entry: {str(e)}")
    finally:
        cursor.close()
        conn.close()


# ----------------------------------------------------------------
# Literature browsing & management (/literature page)
# ----------------------------------------------------------------
# Browsing is public - anyone can look up what's in the reference
# library. Adding new entries reuses the existing require_contributor
# endpoint above. Editing and deleting existing entries, and
# assigning/unassigning a reference to taxa, are superuser-only.

@app.get("/api/v1/literature")
def list_literature(
    q: Optional[str] = Query(None, description="Optional fuzzy filter across author, title, year, publication"),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """
    Paginated browse listing for the /literature page - every column
    on the literature table (not just a formatted citation string, as
    /api/v1/literature/search returns), optionally filtered by the
    same fuzzy search used elsewhere. With no query, returns entries
    newest-first so the most recently catalogued references surface
    first.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if q:
            cursor.execute("""
                SELECT *, similarity(search_text, %s) AS sim
                FROM literature
                WHERE search_text %% %s OR search_text ILIKE %s
                ORDER BY
                    CASE WHEN search_text ILIKE %s THEN 0 ELSE 1 END,
                    sim DESC
                LIMIT %s OFFSET %s;
            """, (q, q, f"%{q}%", f"%{q}%", limit, offset))
        else:
            cursor.execute("""
                SELECT * FROM literature
                ORDER BY "yearPublished" DESC NULLS LAST, "authorName" ASC
                LIMIT %s OFFSET %s;
            """, (limit, offset))
        rows = cursor.fetchall()

        count_cursor_sql = "SELECT COUNT(*) AS total FROM literature" + (" WHERE search_text %% %s OR search_text ILIKE %s" if q else "")
        count_params = (q, f"%{q}%") if q else ()
        cursor.execute(count_cursor_sql, count_params)
        total = cursor.fetchone()["total"]

        return {"results": rows, "total": total, "limit": limit, "offset": offset}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query error: {str(e)}")
    finally:
        cursor.close()
        conn.close()


@app.get("/api/v1/literature/{lit_id}")
def get_literature_detail(lit_id: str):
    """
    Full detail for one literature entry, plus how many places it's
    cited from (observations, samples, taxa) and exactly which taxa -
    used by the /literature page's detail view, and to decide whether
    deletion should be allowed.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT * FROM literature WHERE "litID" = %s;', (lit_id,))
        entry = cursor.fetchone()
        if not entry:
            raise HTTPException(status_code=404, detail=f"No literature entry found with litID {lit_id}")

        cursor.execute('SELECT COUNT(*) AS n FROM observation_literature_junction WHERE "litID" = %s;', (lit_id,))
        obs_count = cursor.fetchone()["n"]
        cursor.execute('SELECT COUNT(*) AS n FROM sample_literature_junction WHERE "litID" = %s;', (lit_id,))
        sample_count = cursor.fetchone()["n"]
        cursor.execute("""
            SELECT j.taxonid AS taxon_id, t."scientificName" AS scientific_name, j."Type" AS type
            FROM taxonomy_literature_junction j
            JOIN taxonomy t ON j.taxonid = t."taxonID"
            WHERE j."litID" = %s
            ORDER BY t."scientificName";
        """, (lit_id,))
        linked_taxa = cursor.fetchall()

        return {
            "entry": entry,
            "usage": {
                "observations": obs_count,
                "samples": sample_count,
                "taxa": len(linked_taxa)
            },
            "linked_taxa": linked_taxa
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query error: {str(e)}")
    finally:
        cursor.close()
        conn.close()


@app.put("/api/v1/literature/{lit_id}")
def edit_literature(lit_id: str, payload: LiteratureSubmission, user: dict = Depends(require_superuser)):
    """
    Edits an existing literature entry (fixing a typo, filling in a
    missing DOI, etc). Full-replace, like the taxonomy editor's PUT -
    logged to admin_activity_log with a field-by-field diff.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT * FROM literature WHERE "litID" = %s;', (lit_id,))
        current = cursor.fetchone()
        if not current:
            raise HTTPException(status_code=404, detail=f"No literature entry found with litID {lit_id}")

        new_values = {
            "authorName": payload.authorName, "editorName": payload.editorName,
            "yearPublished": payload.yearPublished, "articleTitle": payload.articleTitle,
            "publicationTitle": payload.publicationTitle, "publicationSeries": payload.publicationSeries,
            "publicationVolume": payload.publicationVolume, "publicationIssue": payload.publicationIssue,
            "publicationTotalpages": payload.publicationTotalpages, "publicationPages": payload.publicationPages,
            "publishedBy": payload.publishedBy, "publicationISBNorISSN": payload.publicationISBNorISSN,
            "publicationDOI": payload.publicationDOI, "sourceURL": payload.sourceURL, "litNotes": payload.litNotes
        }

        field_changes = {}
        for field, new_val in new_values.items():
            if (current[field] or None) != (new_val or None):
                field_changes[field] = {"old": current[field], "new": new_val}

        if not field_changes:
            return {"litID": lit_id, "message": "No changes to save.", "changed_fields": []}

        cursor.execute("""
            UPDATE literature SET
                "authorName" = %s, "editorName" = %s, "yearPublished" = %s, "articleTitle" = %s,
                "publicationTitle" = %s, "publicationSeries" = %s, "publicationVolume" = %s,
                "publicationIssue" = %s, "publicationTotalpages" = %s, "publicationPages" = %s,
                "publishedBy" = %s, "publicationISBNorISSN" = %s, "publicationDOI" = %s,
                "sourceURL" = %s, "litNotes" = %s
            WHERE "litID" = %s;
        """, (
            new_values["authorName"], new_values["editorName"], new_values["yearPublished"], new_values["articleTitle"],
            new_values["publicationTitle"], new_values["publicationSeries"], new_values["publicationVolume"],
            new_values["publicationIssue"], new_values["publicationTotalpages"], new_values["publicationPages"],
            new_values["publishedBy"], new_values["publicationISBNorISSN"], new_values["publicationDOI"],
            new_values["sourceURL"], new_values["litNotes"], lit_id
        ))

        cursor.execute("""
            INSERT INTO admin_activity_log (performed_by_user_id, action_type, table_name, record_id, field_changes, notes)
            VALUES (%s, %s, %s, %s, %s::jsonb, %s);
        """, (user["user_id"], "literature_edit", "literature", lit_id, json.dumps(field_changes), None))

        conn.commit()
        return {"litID": lit_id, "message": "Saved.", "changed_fields": list(field_changes.keys())}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Could not save literature entry: {str(e)}")
    finally:
        cursor.close()
        conn.close()


@app.delete("/api/v1/literature/{lit_id}")
def delete_literature(lit_id: str, user: dict = Depends(require_superuser)):
    """
    Deletes a literature entry outright - only allowed when nothing
    still cites it (no observations, samples, or taxa reference this
    litID), so deletion can never silently orphan a citation
    elsewhere. If it's still in use, the error message says exactly
    where, so the superuser knows what to unlink first.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT 1 FROM literature WHERE "litID" = %s;', (lit_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail=f"No literature entry found with litID {lit_id}")

        cursor.execute('SELECT COUNT(*) AS n FROM observation_literature_junction WHERE "litID" = %s;', (lit_id,))
        obs_count = cursor.fetchone()["n"]
        cursor.execute('SELECT COUNT(*) AS n FROM sample_literature_junction WHERE "litID" = %s;', (lit_id,))
        sample_count = cursor.fetchone()["n"]
        cursor.execute('SELECT COUNT(*) AS n FROM taxonomy_literature_junction WHERE "litID" = %s;', (lit_id,))
        taxon_count = cursor.fetchone()["n"]

        if obs_count or sample_count or taxon_count:
            parts = []
            if obs_count: parts.append(f"{obs_count} observation(s)")
            if sample_count: parts.append(f"{sample_count} sample(s)")
            if taxon_count: parts.append(f"{taxon_count} taxon/taxa")
            raise HTTPException(
                status_code=400,
                detail=f"Cannot delete - still cited by {', '.join(parts)}. Unlink it from those first."
            )

        cursor.execute('DELETE FROM literature WHERE "litID" = %s;', (lit_id,))

        cursor.execute("""
            INSERT INTO admin_activity_log (performed_by_user_id, action_type, table_name, record_id, field_changes, notes)
            VALUES (%s, %s, %s, %s, %s::jsonb, %s);
        """, (user["user_id"], "literature_delete", "literature", lit_id, json.dumps({}), None))

        conn.commit()
        return {"message": "Literature entry deleted."}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Could not delete literature entry: {str(e)}")
    finally:
        cursor.close()
        conn.close()


@app.get("/api/v1/projects/search")
def search_projects(
    q: str = Query(..., min_length=2, description="Fuzzy search across project name"),
    limit: int = Query(15, ge=1, le=50)
):
    """
    Fuzzy search across recording_projects, for the "choose a project"
    picker on the sample submission form.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT
                project_id, project_name, project_category, website_url,
                similarity(project_name, %s) AS sim
            FROM recording_projects
            WHERE project_name %% %s OR project_name ILIKE %s
            ORDER BY
                CASE WHEN project_name ILIKE %s THEN 0 ELSE 1 END,
                sim DESC
            LIMIT %s;
        """, (q, q, f"%{q}%", f"%{q}%", limit))
        rows = cursor.fetchall()
        return {"query": q, "count": len(rows), "results": rows}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query error: {str(e)}")
    finally:
        cursor.close()
        conn.close()


@app.get("/api/v1/projects")
def list_projects(
    q: Optional[str] = Query(None, description="Optional fuzzy filter across project name"),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """
    Paginated browse listing for the Projects tab on /literature -
    mirrors list_literature. With no query, returns newest-first.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if q:
            cursor.execute("""
                SELECT *, similarity(project_name, %s) AS sim
                FROM recording_projects
                WHERE project_name %% %s OR project_name ILIKE %s
                ORDER BY
                    CASE WHEN project_name ILIKE %s THEN 0 ELSE 1 END,
                    sim DESC
                LIMIT %s OFFSET %s;
            """, (q, q, f"%{q}%", f"%{q}%", limit, offset))
        else:
            cursor.execute("""
                SELECT * FROM recording_projects
                ORDER BY entered_at DESC NULLS LAST, project_name ASC
                LIMIT %s OFFSET %s;
            """, (limit, offset))
        rows = cursor.fetchall()

        count_sql = "SELECT COUNT(*) AS total FROM recording_projects" + (" WHERE project_name %% %s OR project_name ILIKE %s" if q else "")
        count_params = (q, f"%{q}%") if q else ()
        cursor.execute(count_sql, count_params)
        total = cursor.fetchone()["total"]

        return {"results": rows, "total": total, "limit": limit, "offset": offset}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query error: {str(e)}")
    finally:
        cursor.close()
        conn.close()


@app.get("/api/v1/projects/{project_id}")
def get_project_detail(project_id: int):
    """
    Full detail for one project, plus how many samples cite it as
    their source, for the Projects tab's detail view.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM recording_projects WHERE project_id = %s;", (project_id,))
        entry = cursor.fetchone()
        if not entry:
            raise HTTPException(status_code=404, detail=f"No project found with id {project_id}")

        cursor.execute("SELECT COUNT(*) AS n FROM sample_project_junction WHERE project_id = %s;", (project_id,))
        sample_count = cursor.fetchone()["n"]

        return {"entry": entry, "usage": {"samples": sample_count}}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query error: {str(e)}")
    finally:
        cursor.close()
        conn.close()


@app.post("/api/v1/projects")
def create_project(payload: ProjectSubmission, user: dict = Depends(require_contributor)):
    """
    Adds a new recording project/survey/records-centre-bulk-download -
    used when a contributor's sample comes from a formal project that
    isn't already catalogued.
    """
    valid_categories = {"Survey or monitoring programme", "Biological records centre bulk download"}
    if payload.project_category not in valid_categories:
        raise HTTPException(status_code=400, detail=f"project_category must be one of {sorted(valid_categories)}")

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO recording_projects (project_name, project_category, website_url, description, submitted_by_user_id)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING project_id;
        """, (payload.project_name, payload.project_category, payload.website_url, payload.description, user["user_id"]))
        new_id = cursor.fetchone()["project_id"]
        conn.commit()
        return {"project_id": new_id}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Could not create project: {str(e)}")
    finally:
        cursor.close()
        conn.close()


@app.post("/api/v1/submit/observation")
def submit_observation(payload: ObservationSubmission, user: dict = Depends(require_contributor)):
    """
    Adds one observation (one species record) to an existing sample.
    Call this repeatedly with the same eventID to record multiple
    species found in the same sample - this is the "add another
    observation from this sample" pattern from the project's aims.
    Only allows adding to a sample this same user submitted, so
    people can't add records into someone else's sample.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT submitted_by_user_id FROM samples WHERE "eventID" = %s;', (payload.eventID,))
        sample = cursor.fetchone()
        if not sample:
            raise HTTPException(status_code=404, detail="No such sample (eventID)")
        if sample["submitted_by_user_id"] != user["user_id"]:
            raise HTTPException(status_code=403, detail="You can only add observations to your own submitted samples")

        cursor.execute("SELECT nextval('web_observationid_seq');")
        new_id = f"WEB-{cursor.fetchone()['nextval']}"

        cursor.execute("""
            INSERT INTO observations (
                "observationID", "eventID", "taxonID", "identifiedBy",
                "identificationVerificationStatus", "identificationRemarks",
                "basisOfRecord", "idTechnique", "idText[free_text]",
                verification_status, submitted_by_user_id, entered_by, entered_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending', %s, %s, CURRENT_TIMESTAMP
            );
        """, (
            new_id, payload.eventID, payload.taxonID, payload.identifiedBy,
            payload.identificationVerificationStatus, payload.identificationRemarks,
            payload.basisOfRecord, payload.idTechnique, payload.idText,
            user["user_id"], user["display_name"]
        ))
        conn.commit()
        return {"observationID": new_id, "eventID": payload.eventID, "status": "pending"}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Could not create observation: {str(e)}")
    finally:
        cursor.close()
        conn.close()

@app.put("/api/v1/submit/observation/{observation_id}")
def edit_own_observation(observation_id: str, payload: ObservationSelfEditSubmission, user: dict = Depends(require_contributor)):
    """
    Lets a contributor edit their own observation's identification
    while it's still 'pending' - covers changing your mind about a
    species ID, or fixing a typo, while still in the process of
    entering demographics/specimens for it. Once a superuser has
    reviewed the observation (accepted/rejected/reassigned), it's
    frozen here and any further change goes through the audited
    review workflow instead (submit_verification_action), so nothing
    can be quietly altered after someone else has signed off on it.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT * FROM observations WHERE "observationID" = %s;', (observation_id,))
        current = cursor.fetchone()
        if not current:
            raise HTTPException(status_code=404, detail="No such observation")
        if current["submitted_by_user_id"] != user["user_id"]:
            raise HTTPException(status_code=403, detail="You can only edit your own submitted observations")
        if current["verification_status"] != "pending":
            raise HTTPException(status_code=409, detail="This observation has already been reviewed and can no longer be edited here")

        cursor.execute('SELECT 1 FROM taxonomy WHERE "taxonID" = %s;', (payload.taxonID,))
        if not cursor.fetchone():
            raise HTTPException(status_code=400, detail="taxonID does not match any taxon")

        cursor.execute("""
            UPDATE observations SET
                "taxonID" = %s, "identifiedBy" = %s,
                "identificationVerificationStatus" = %s, "identificationRemarks" = %s,
                "basisOfRecord" = %s, "idTechnique" = %s, "idText[free_text]" = %s
            WHERE "observationID" = %s;
        """, (
            payload.taxonID, payload.identifiedBy,
            payload.identificationVerificationStatus, payload.identificationRemarks,
            payload.basisOfRecord, payload.idTechnique, payload.idText,
            observation_id
        ))
        conn.commit()
        return {"observationID": observation_id, "message": "Updated."}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Could not update observation: {str(e)}")
    finally:
        cursor.close()
        conn.close()

@app.post("/api/v1/submit/demographic")
def submit_demographic(payload: DemographicSubmission, user: dict = Depends(require_contributor)):
    """
    Adds one demographic group (e.g. "1 female adult") to an existing
    observation. Call this repeatedly with the same observationID if
    an observation contains more than one demographic group (e.g. "3
    male nymphs" AND "1 female adult" from the same sample).
    Only allows adding to an observation this same user submitted.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT submitted_by_user_id FROM observations WHERE "observationID" = %s;', (payload.observationID,))
        obs = cursor.fetchone()
        if not obs:
            raise HTTPException(status_code=404, detail="No such observation (observationID)")
        if obs["submitted_by_user_id"] != user["user_id"]:
            raise HTTPException(status_code=403, detail="You can only add demographic details to your own submitted observations")

        cursor.execute("SELECT nextval('web_demographicid_seq');")
        new_id = f"WEB-{cursor.fetchone()['nextval']}"

        cursor.execute("""
            INSERT INTO observation_demographics (
                "demographicID", "observationID", sex, lifestage, count,
                density, "densityUnit", "minCount", "maxCount", "countDescription"
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            );
        """, (
            new_id, payload.observationID, payload.sex, payload.lifestage, payload.count,
            payload.density, payload.densityUnit, payload.minCount, payload.maxCount, payload.countDescription
        ))
        conn.commit()
        return {"demographicID": new_id, "observationID": payload.observationID}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Could not create demographic group: {str(e)}")
    finally:
        cursor.close()
        conn.close()


@app.post("/api/v1/submit/specimen")
def submit_specimen(payload: SpecimenSubmission, user: dict = Depends(require_contributor)):
    """
    Adds one physical specimen record to an existing demographic group.
    A demographic group can contain more than one specimen record (e.g.
    if several individuals from the same group were each retained and
    catalogued separately) - call this repeatedly with the same
    demographicID for each one.
    Ownership is checked by following demographicID -> observationID ->
    submitted_by_user_id, since specimens don't record the submitter
    directly - only allows adding to your own submitted material.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT o.submitted_by_user_id
            FROM observation_demographics d
            JOIN observations o ON d."observationID" = o."observationID"
            WHERE d."demographicID" = %s;
        """, (payload.demographicID,))
        demographic = cursor.fetchone()
        if not demographic:
            raise HTTPException(status_code=404, detail="No such demographic group (demographicID)")
        if demographic["submitted_by_user_id"] != user["user_id"]:
            raise HTTPException(status_code=403, detail="You can only add specimens to your own submitted material")

        cursor.execute("SELECT nextval('web_specimenid_seq');")
        new_id = f"WEB-{cursor.fetchone()['nextval']}"

        cursor.execute("""
            INSERT INTO specimens (
                "specimenID", "demographicID", "specCount", "specLocation",
                "specRef", "specPreservation", "specType", "specComments"
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s
            );
        """, (
            new_id, payload.demographicID, payload.specCount, payload.specLocation,
            payload.specRef, payload.specPreservation, payload.specType, payload.specComments
        ))
        conn.commit()
        return {"specimenID": new_id, "demographicID": payload.demographicID}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Could not create specimen record: {str(e)}")
    finally:
        cursor.close()
        conn.close()


@app.get("/api/v1/submit/my-pending")
def list_my_pending(user: dict = Depends(require_contributor)):
    """
    Lists everything the logged-in user has submitted that's still
    pending review - both samples and the observations within them -
    so they can review, edit, or withdraw before it's checked by a
    superuser.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT
                o."observationID", o."eventID", o."taxonID",
                t."scientificName", o.verification_status, o.entered_at
            FROM observations o
            JOIN taxonomy t ON o."taxonID" = t."taxonID"
            WHERE o.submitted_by_user_id = %s AND o.verification_status = 'pending'
            ORDER BY o.entered_at DESC;
        """, (user["user_id"],))
        return {"pending_observations": cursor.fetchall()}
    finally:
        cursor.close()
        conn.close()


@app.get("/api/v1/submit/my-samples")
def list_my_samples(user: dict = Depends(require_contributor)):
    """
    Lists every sample the logged-in user has submitted (regardless of
    whether its observations are still pending, or already reviewed),
    with that sample's own observations nested inside it under
    "observations" - and each observation's own demographic groups
    nested under IT as "demographics", each of which has its own
    specimen records nested as "specimens". Unlike /my-pending (which
    returns a flat list of observations only, with no sample-level
    details), this gives the submission page everything it needs to:
      - show "your submissions" as the full natural tree: sample ->
        observations -> demographic groups -> specimens
      - offer "use this sample as a starting point for a new one",
        since all the sample-level fields are present here to copy
      - let a contributor add another observation, demographic group,
        or specimen to something they already started, directly from
        this list, without needing to remember any of its IDs
    Only ever returns this user's own samples - never anyone else's.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT
                "eventID", "samplingLocation", "decimalLatitude", "decimalLongitude",
                "coordinateuncertaintyinmeters" AS "coordinateUncertaintyInMeters",
                "earliestDateCollected", "latestDateCollected",
                "habitat", "microhabitat", "SHADe", "samplingProtocol",
                "samplesizeValue", "samplesizeUnit", "datarestricted", "licenceHolder",
                "recordedBy", "eventRemarks", entered_at
            FROM samples
            WHERE submitted_by_user_id = %s
            ORDER BY entered_at DESC;
        """, (user["user_id"],))
        samples = cursor.fetchall()

        cursor.execute("""
            SELECT
                o."observationID", o."eventID", o."taxonID",
                t."scientificName", o.verification_status, o.entered_at
            FROM observations o
            JOIN taxonomy t ON o."taxonID" = t."taxonID"
            WHERE o.submitted_by_user_id = %s
            ORDER BY o.entered_at ASC;
        """, (user["user_id"],))
        observations = cursor.fetchall()

        # Demographics and specimens don't record submitted_by_user_id
        # directly, so we reach them by following observationID (and
        # then demographicID) back to the observations this user owns -
        # simplest to just pull every demographic/specimen row attached
        # to any observation already known to be theirs, from above.
        observation_ids = [o["observationID"] for o in observations]
        demographics = []
        specimens = []
        if observation_ids:
            cursor.execute("""
                SELECT "demographicID", "observationID", sex, lifestage, count,
                       density, "densityUnit", "minCount", "maxCount", "countDescription"
                FROM observation_demographics
                WHERE "observationID" = ANY(%s)
                ORDER BY "demographicID" ASC;
            """, (observation_ids,))
            demographics = cursor.fetchall()

            demographic_ids = [d["demographicID"] for d in demographics]
            if demographic_ids:
                cursor.execute("""
                    SELECT "specimenID", "demographicID", "specCount", "specLocation",
                           "specRef", "specPreservation", "specType", "specComments"
                    FROM specimens
                    WHERE "demographicID" = ANY(%s)
                    ORDER BY "specimenID" ASC;
                """, (demographic_ids,))
                specimens = cursor.fetchall()

        # Nest specimens under their demographic group...
        specimens_by_demo = {}
        for spec in specimens:
            specimens_by_demo.setdefault(spec["demographicID"], []).append(spec)
        for demo in demographics:
            demo["specimens"] = specimens_by_demo.get(demo["demographicID"], [])

        # ...then demographic groups (with their specimens already
        # attached) under their observation...
        demos_by_obs = {}
        for demo in demographics:
            demos_by_obs.setdefault(demo["observationID"], []).append(demo)
        for obs in observations:
            obs["demographics"] = demos_by_obs.get(obs["observationID"], [])

        # ...then observations (with everything already attached) under
        # their parent sample, same as before
        obs_by_event = {}
        for obs in observations:
            obs_by_event.setdefault(obs["eventID"], []).append(obs)

        for sample in samples:
            sample["observations"] = obs_by_event.get(sample["eventID"], [])

        return {"samples": samples}
    finally:
        cursor.close()
        conn.close()


@app.delete("/api/v1/submit/observation/{observation_id}")
def withdraw_observation(observation_id: str, user: dict = Depends(require_contributor)):
    """
    Lets a contributor withdraw (delete) their own observation,
    but ONLY while it's still pending review - once a superuser has
    verified it, it can no longer be silently removed this way.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT submitted_by_user_id, verification_status
            FROM observations WHERE "observationID" = %s;
        """, (observation_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="No such observation")
        if row["submitted_by_user_id"] != user["user_id"]:
            raise HTTPException(status_code=403, detail="You can only withdraw your own submissions")
        if row["verification_status"] != "pending":
            raise HTTPException(status_code=400, detail="Only pending (not yet reviewed) observations can be withdrawn")

        cursor.execute('DELETE FROM observations WHERE "observationID" = %s;', (observation_id,))
        conn.commit()
        return {"message": "Observation withdrawn"}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Could not withdraw: {str(e)}")
    finally:
        cursor.close()
        conn.close()
        
@app.delete("/api/v1/submit/sample/{event_id}")
def withdraw_sample(event_id: str, user: dict = Depends(require_contributor)):
    """
    Lets a contributor withdraw their own sample, PROVIDED every
    observation currently attached to it (if any) is still pending
    review. If even one attached observation has already been
    verified/queried/rejected by a superuser, the whole withdrawal
    is refused - nothing reviewed can be silently removed this way.
    Withdrawing the sample also withdraws any still-pending
    observations attached to it, since an empty orphaned sample
    left behind would serve no purpose.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT submitted_by_user_id FROM samples WHERE "eventID" = %s;', (event_id,))
        sample = cursor.fetchone()
        if not sample:
            raise HTTPException(status_code=404, detail="No such sample")
        if sample["submitted_by_user_id"] != user["user_id"]:
            raise HTTPException(status_code=403, detail="You can only withdraw your own submitted samples")

        cursor.execute("""
            SELECT COUNT(*) AS non_pending_count
            FROM observations
            WHERE "eventID" = %s AND verification_status != 'pending';
        """, (event_id,))
        if cursor.fetchone()["non_pending_count"] > 0:
            raise HTTPException(
                status_code=400,
                detail="Cannot withdraw: this sample has at least one observation that has already been reviewed"
            )

        cursor.execute('DELETE FROM observations WHERE "eventID" = %s;', (event_id,))
        cursor.execute('DELETE FROM samples WHERE "eventID" = %s;', (event_id,))
        conn.commit()
        return {"message": f"Sample {event_id} and any pending observations within it were withdrawn"}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Could not withdraw sample: {str(e)}")
    finally:
        cursor.close()
        conn.close()


# ==========================================================
# VERIFICATION / REVIEW (superuser only)
# ==========================================================
# Every review decision is written as a new row in
# observation_verification_actions rather than overwriting a single
# status field - this keeps a full, permanent history of who reviewed
# what, when, what they decided, and why. observations.verification_status
# (and its verified_by/verified_date/verification_notes companions)
# are kept in sync as a convenience snapshot of the MOST RECENT action,
# since a lot of existing code (map filtering, the submission page's
# pending list) already reads that single field - but the actions
# table is now the source of truth for anything needing history.

@app.get("/api/v1/admin/review-queue")
def get_review_queue(user: dict = Depends(require_superuser)):
    """
    Returns every sample that has at least one pending observation,
    across ALL contributors (not just the current user) - this is the
    superuser's queue of work still waiting for a decision. Each
    sample includes ALL of its observations (not just the pending
    ones) so a reviewer has full context on the sample as a whole, each
    with its demographics/specimens nested the same way the
    contributor's own submission page shows them, plus who submitted
    it.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT DISTINCT s."eventID"
            FROM samples s
            JOIN observations o ON o."eventID" = s."eventID"
            WHERE o.verification_status = 'pending';
        """)
        event_ids = [row["eventID"] for row in cursor.fetchall()]

        if not event_ids:
            return {"samples": []}

        cursor.execute("""
            SELECT
                s."eventID", s."samplingLocation", s."decimalLatitude", s."decimalLongitude",
                s."earliestDateCollected", s."latestDateCollected", s."habitat", s."microhabitat",
                s."SHADe", s."samplingProtocol", s."recordedBy", s."eventRemarks", s.entered_at,
                u.display_name AS submitted_by_name, u.email AS submitted_by_email
            FROM samples s
            LEFT JOIN users u ON s.submitted_by_user_id = u.user_id
            WHERE s."eventID" = ANY(%s)
            ORDER BY s.entered_at ASC;
        """, (event_ids,))
        samples = cursor.fetchall()

        cursor.execute("""
            SELECT
                o."observationID", o."eventID", o."taxonID", t."scientificName", o.proposed_taxon_name,
                o."identifiedBy", o."identificationVerificationStatus", o."identificationRemarks",
                o."basisOfRecord", o."idTechnique", o."idText[free_text]" AS "idText",
                o.verification_status, o.entered_at,
                u.display_name AS submitted_by_name, u.email AS submitted_by_email
            FROM observations o
            LEFT JOIN taxonomy t ON o."taxonID" = t."taxonID"
            LEFT JOIN users u ON o.submitted_by_user_id = u.user_id
            WHERE o."eventID" = ANY(%s)
            ORDER BY o.entered_at ASC;
        """, (event_ids,))
        observations = cursor.fetchall()

        observation_ids = [o["observationID"] for o in observations]
        demographics, specimens = [], []
        if observation_ids:
            cursor.execute("""
                SELECT "demographicID", "observationID", sex, lifestage, count,
                       density, "densityUnit", "minCount", "maxCount", "countDescription"
                FROM observation_demographics
                WHERE "observationID" = ANY(%s)
                ORDER BY "demographicID" ASC;
            """, (observation_ids,))
            demographics = cursor.fetchall()

            demographic_ids = [d["demographicID"] for d in demographics]
            if demographic_ids:
                cursor.execute("""
                    SELECT "specimenID", "demographicID", "specCount", "specLocation",
                           "specRef", "specPreservation", "specType", "specComments"
                    FROM specimens
                    WHERE "demographicID" = ANY(%s)
                    ORDER BY "specimenID" ASC;
                """, (demographic_ids,))
                specimens = cursor.fetchall()

        specimens_by_demo = {}
        for spec in specimens:
            specimens_by_demo.setdefault(spec["demographicID"], []).append(spec)
        for demo in demographics:
            demo["specimens"] = specimens_by_demo.get(demo["demographicID"], [])

        demos_by_obs = {}
        for demo in demographics:
            demos_by_obs.setdefault(demo["observationID"], []).append(demo)
        for obs in observations:
            obs["demographics"] = demos_by_obs.get(obs["observationID"], [])

        obs_by_event = {}
        for obs in observations:
            obs_by_event.setdefault(obs["eventID"], []).append(obs)
        for sample in samples:
            sample["observations"] = obs_by_event.get(sample["eventID"], [])

        return {"samples": samples}
    finally:
        cursor.close()
        conn.close()


@app.get("/api/v1/admin/unresolved-taxa")
def get_unresolved_taxa(user: dict = Depends(require_superuser)):
    """
    Lists every observation still awaiting taxon resolution
    (taxonID IS NULL, proposed_taxon_name IS NOT NULL) - almost
    always the result of a batch upload where the typed species name
    didn't exactly match anything already in the taxonomy table.
    Deliberately independent of verification_status: a superuser's
    own batch upload gets auto-verified immediately, but the taxon
    itself can still be genuinely unresolved and need the same
    attention as a contributor's pending one.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT
                o."observationID", o."eventID", o.proposed_taxon_name, o.verification_status, o.entered_at,
                s."samplingLocation", s."earliestDateCollected",
                u.display_name AS submitted_by_name
            FROM observations o
            LEFT JOIN samples s ON o."eventID" = s."eventID"
            LEFT JOIN users u ON o.submitted_by_user_id = u.user_id
            WHERE o."taxonID" IS NULL AND o.proposed_taxon_name IS NOT NULL
            ORDER BY o.entered_at ASC;
        """)
        rows = cursor.fetchall()
        return {"count": len(rows), "observations": rows}
    finally:
        cursor.close()
        conn.close()


@app.post("/api/v1/admin/verify/{observation_id}")
def submit_verification_action(
    observation_id: str,
    payload: VerificationActionSubmission,
    user: dict = Depends(require_superuser)
):
    """
    Records a review decision on an observation: accept, reject,
    reassign to a different taxon, or query (ask the contributor for
    more information) - always as a NEW row in
    observation_verification_actions, never overwriting history.
    Also updates observations' own status fields to match (so existing
    code that reads verification_status directly still works), and -
    for a reassignment specifically - writes the corrected taxon into
    observation_taxonomy_override, which is the table that actually
    controls what taxon this observation resolves to everywhere else
    in the site (view_effective_observations, the map, etc.).
    """
    valid_actions = {"accepted", "rejected", "reassigned", "queried"}
    if payload.action_type not in valid_actions:
        raise HTTPException(status_code=400, detail=f"action_type must be one of {sorted(valid_actions)}")
    if payload.action_type == "reassigned" and not payload.reassigned_taxon_id:
        raise HTTPException(status_code=400, detail="reassigned_taxon_id is required when action_type is 'reassigned'")

    status_by_action = {
        "accepted": "verified",
        "rejected": "rejected",
        "reassigned": "verified",
        "queried": "queried",
    }

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT "observationID" FROM observations WHERE "observationID" = %s;', (observation_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="No such observation")

        if payload.reassigned_taxon_id:
            cursor.execute('SELECT "taxonID" FROM taxonomy WHERE "taxonID" = %s;', (payload.reassigned_taxon_id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="reassigned_taxon_id does not match any taxon")

        # 1. Log the action - this is the permanent record
        cursor.execute("""
            INSERT INTO observation_verification_actions (
                "observationID", action_type, reassigned_taxon_id, notes, performed_by_user_id
            ) VALUES (%s, %s, %s, %s, %s);
        """, (observation_id, payload.action_type, payload.reassigned_taxon_id, payload.notes, user["user_id"]))

        # 2. Update the observation's own snapshot fields to match, so
        # existing code reading verification_status directly still works
        cursor.execute("""
            UPDATE observations
            SET verification_status = %s,
                verified_by = %s,
                verified_date = CURRENT_TIMESTAMP,
                verification_notes = %s
            WHERE "observationID" = %s;
        """, (status_by_action[payload.action_type], user["display_name"], payload.notes, observation_id))

        # 3. For a reassignment, update (or create) the override that
        # actually controls this observation's effective taxon
        if payload.action_type == "reassigned":
            cursor.execute(
                'SELECT 1 FROM observation_taxonomy_override WHERE observation_id = %s;',
                (observation_id,)
            )
            if cursor.fetchone():
                cursor.execute("""
                    UPDATE observation_taxonomy_override
                    SET revised_taxon_id = %s, reason_or_notes = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE observation_id = %s;
                """, (payload.reassigned_taxon_id, payload.notes, observation_id))
            else:
                cursor.execute("""
                    INSERT INTO observation_taxonomy_override (observation_id, revised_taxon_id, reason_or_notes)
                    VALUES (%s, %s, %s);
                """, (observation_id, payload.reassigned_taxon_id, payload.notes))

        conn.commit()
        return {"observationID": observation_id, "action_type": payload.action_type, "new_status": status_by_action[payload.action_type]}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Could not record verification action: {str(e)}")
    finally:
        cursor.close()
        conn.close()


# ==========================================================
# TAXONOMY EDITOR (superuser only)
# ==========================================================
# Lets a superuser rename taxa, change rank/status, reparent them
# within the hierarchy, mark them as synonyms of another taxon, or
# create brand new taxa - all through the GUI at /admin/taxonomy,
# rather than needing a hand-written SQL migration for routine
# taxonomic maintenance. Every change is written to
# admin_activity_log as a permanent, append-only record of exactly
# what changed, who changed it, and why (their optional notes) - the
# same audit-trail pattern already used for observation verification.
#
# Reads for the editor reuse the existing public endpoints
# (/api/v1/taxonomy/detail/{id}, /api/v1/taxonomy/search,
# /api/v1/taxonomy/children/{id}) - only the writes below are new.

VALID_TAXONOMIC_STATUSES = {"accepted", "synonym", "misapplied", "doubtful"}

VALID_TAXON_LITERATURE_TYPES = {
    "Taxonomy or synonymy from",
    "Name first published in",
    "As used in",
    "Presence in UK from",
    "Identification Key",
}

# Observation-level literature links are about this specific record's
# determination, not about where the record itself came from (that's
# the sample's source-of-record / literature link instead - see
# sample_literature_junction).
VALID_OBSERVATION_LITERATURE_TYPES = {
    "Identified using",              # the key/reference used to determine this specimen
    "Determination confirmed in",    # a later taxonomic revision or expert paper that confirms/reassigns this specific determination
    "First published record in",     # this record is itself the subject of a published note (e.g. a first county/country record)
    "Discussed in",                  # a later paper discusses this specific record
}

VALID_NOMENCLATURAL_STATUSES = {
    "invalid - junior synonym",
    "invalid - literature misspelling",
    "invalid - misspelled or invalid basionym",
    "invalid - misspelled or invalid junior synonym",
    "invalid - subsequent combination of basionym",
    "invalid - subsequent combination of junior synonym",
    "invalid - superseded basionym",
    "nomen dubium",
    "nomen nudum",
    "species inquirenda",
    "valid name with subgenus",
}


def _get_ancestor_id_set(cursor, taxon_id: str) -> set:
    """Small helper: the set of taxonIDs in a taxon's ancestor chain,
    used to block reparenting moves that would create a cycle (i.e.
    setting a taxon's parent to one of its own descendants)."""
    cursor.execute("SELECT * FROM get_ancestor_chain(%s);", (taxon_id,))
    return {r["taxon_id"] for r in cursor.fetchall()}


@app.put("/api/v1/admin/taxonomy/{taxon_id}")
def edit_taxonomy(
    taxon_id: str,
    payload: TaxonomyEditSubmission,
    user: dict = Depends(require_superuser)
):
    """
    Saves edits to an existing taxon: name/authorship/rank/status
    changes, reparenting within the hierarchy, or marking it as a
    synonym of another taxon. Validates that reparenting can't create
    a circular chain of ancestry, and that synonymy always points
    directly at a genuinely accepted taxon (never at another
    synonym). If the taxon being synonymised has children that are
    themselves already synonyms (e.g. it's a species with a dozen
    older names synonymised under it), those are automatically
    re-pointed to the new accepted name rather than blocking the
    edit - only children that are still valid taxa in their own
    right (e.g. a subspecies or variety) block the edit, since those
    need a human decision about where they belong. Logs a
    field-by-field diff of whatever changed to admin_activity_log.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT * FROM taxonomy WHERE "taxonID" = %s;', (taxon_id,))
        current = cursor.fetchone()
        if not current:
            raise HTTPException(status_code=404, detail=f"No taxon found with taxonID {taxon_id}")

        new_values = {
            "scientificName": (payload.scientificName or "").strip() or None,
            "scientificnameAuthorship": (payload.scientificnameAuthorship or "").strip() or None,
            "taxonrank": (payload.taxonrank or "").strip() or None,
            "taxonomicStatus": (payload.taxonomicStatus or "").strip() or None,
            "nomenclaturalStatus": (payload.nomenclaturalStatus or "").strip() or None,
            "taxonRemarks": (payload.taxonRemarks or "").strip() or None,
            "parentNameUsageID": (payload.parentNameUsageID or "").strip() or None,
            "acceptedNameUsageID": (payload.acceptedNameUsageID or "").strip() or None,
        }

        if not new_values["scientificName"]:
            raise HTTPException(status_code=400, detail="scientificName is required")
        if not new_values["taxonrank"]:
            raise HTTPException(status_code=400, detail="taxonrank is required")
        if new_values["taxonomicStatus"] and new_values["taxonomicStatus"] not in VALID_TAXONOMIC_STATUSES:
            raise HTTPException(status_code=400, detail=f"taxonomicStatus must be one of {sorted(VALID_TAXONOMIC_STATUSES)}")
        if new_values["nomenclaturalStatus"] and new_values["nomenclaturalStatus"] not in VALID_NOMENCLATURAL_STATUSES:
            raise HTTPException(status_code=400, detail=f"nomenclaturalStatus must be one of {sorted(VALID_NOMENCLATURAL_STATUSES)}")

        # --- Reparenting validation ---
        new_parent = new_values["parentNameUsageID"]
        if new_parent and new_parent != current["parentNameUsageID"]:
            if new_parent == taxon_id:
                raise HTTPException(status_code=400, detail="A taxon cannot be its own parent")
            cursor.execute('SELECT "taxonID", "acceptedNameUsageID" FROM taxonomy WHERE "taxonID" = %s;', (new_parent,))
            parent_row = cursor.fetchone()
            if not parent_row:
                raise HTTPException(status_code=400, detail="parentNameUsageID does not match any taxon")
            if parent_row["acceptedNameUsageID"] is not None:
                raise HTTPException(status_code=400, detail="Cannot set the parent to a taxon that is itself a synonym - point to its accepted name instead")
            if taxon_id in _get_ancestor_id_set(cursor, new_parent):
                raise HTTPException(status_code=400, detail="That would create a circular parentage - the new parent is a descendant of this taxon")

        # --- Synonymy validation, plus automatic cascade of any
        # synonym children onto the new accepted name ---
        new_accepted = new_values["acceptedNameUsageID"]
        cascaded_synonym_children = []
        if new_accepted and new_accepted != current["acceptedNameUsageID"]:
            if new_accepted == taxon_id:
                raise HTTPException(status_code=400, detail="A taxon cannot be a synonym of itself")
            cursor.execute('SELECT "taxonID", "acceptedNameUsageID" FROM taxonomy WHERE "taxonID" = %s;', (new_accepted,))
            accepted_row = cursor.fetchone()
            if not accepted_row:
                raise HTTPException(status_code=400, detail="acceptedNameUsageID does not match any taxon")
            if accepted_row["acceptedNameUsageID"] is not None:
                raise HTTPException(status_code=400, detail="Cannot mark this as a synonym of another synonym - point to the accepted name directly")

            cursor.execute(
                'SELECT "taxonID", "scientificName", "acceptedNameUsageID" FROM taxonomy WHERE "parentNameUsageID" = %s;',
                (taxon_id,)
            )
            children = cursor.fetchall()
            # A child is still "valid" (blocks the edit) if it has no
            # acceptedNameUsageID of its own - i.e. it's a genuine
            # lower taxon (subspecies, variety, forma...), not just a
            # synonym parked here for browsing. Synonym children carry
            # their own acceptedNameUsageID (normally == taxon_id) and
            # can simply be re-pointed at the new accepted name.
            valid_children = [c for c in children if c["acceptedNameUsageID"] is None]
            synonym_children = [c for c in children if c["acceptedNameUsageID"] is not None]

            if valid_children:
                names = ", ".join(c["scientificName"] for c in valid_children[:5])
                more = f" (+{len(valid_children) - 5} more)" if len(valid_children) > 5 else ""
                raise HTTPException(
                    status_code=400,
                    detail=f"This taxon still has valid (non-synonym) children in the hierarchy - reparent them elsewhere before marking it as a synonym, e.g. {names}{more}"
                )

            if synonym_children:
                child_ids = [c["taxonID"] for c in synonym_children]
                cursor.execute("""
                    UPDATE taxonomy
                    SET "acceptedNameUsageID" = %s, "parentNameUsageID" = %s
                    WHERE "taxonID" = ANY(%s);
                """, (new_accepted, new_accepted, child_ids))
                cascaded_synonym_children = [
                    {"taxonID": c["taxonID"], "scientificName": c["scientificName"]} for c in synonym_children
                ]

        # --- Diff against current values, for the audit log ---
        field_changes = {}
        for field, new_val in new_values.items():
            if (current[field] or None) != (new_val or None):
                field_changes[field] = {"old": current[field], "new": new_val}
        if cascaded_synonym_children:
            field_changes["cascaded_synonym_children"] = cascaded_synonym_children

        if not field_changes:
            return {"taxonID": taxon_id, "message": "No changes to save.", "changed_fields": [], "cascaded_synonym_children": []}

        cursor.execute("""
            UPDATE taxonomy SET
                "scientificName" = %s, "scientificnameAuthorship" = %s, "taxonrank" = %s,
                "taxonomicStatus" = %s, "nomenclaturalStatus" = %s, "taxonRemarks" = %s,
                "parentNameUsageID" = %s, "acceptedNameUsageID" = %s
            WHERE "taxonID" = %s;
        """, (
            new_values["scientificName"], new_values["scientificnameAuthorship"], new_values["taxonrank"],
            new_values["taxonomicStatus"], new_values["nomenclaturalStatus"], new_values["taxonRemarks"],
            new_values["parentNameUsageID"], new_values["acceptedNameUsageID"], taxon_id
        ))

        cursor.execute("""
            INSERT INTO admin_activity_log (performed_by_user_id, action_type, table_name, record_id, field_changes, notes)
            VALUES (%s, %s, %s, %s, %s::jsonb, %s);
        """, (user["user_id"], "taxonomy_edit", "taxonomy", taxon_id, json.dumps(field_changes), payload.notes))

        conn.commit()
        changed_fields = [f for f in field_changes.keys() if f != "cascaded_synonym_children"]
        return {
            "taxonID": taxon_id,
            "message": "Saved.",
            "changed_fields": changed_fields,
            "cascaded_synonym_children": cascaded_synonym_children
        }
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Could not save taxon: {str(e)}")
    finally:
        cursor.close()
        conn.close()


@app.post("/api/v1/admin/taxonomy")
def create_taxonomy(payload: TaxonomyCreateSubmission, user: dict = Depends(require_superuser)):
    """
    Creates a brand new taxon - either a new accepted taxon somewhere
    in the hierarchy (set parentNameUsageID), or a new synonym of an
    existing accepted taxon (set acceptedNameUsageID instead of a
    parent). Gets a WEB-prefixed taxonID, the same convention used
    everywhere else new records are created via the site, so it can
    never collide with a legacy imported taxonID (e.g. 244).

    Optionally attaches one or more literature references in the same
    transaction (payload.literature_links) - since almost every new
    taxon needs at least one supporting reference, the editor page
    lets the person pick these before the taxon exists yet, and they
    get created together rather than needing a separate step.
    """
    if not payload.parentNameUsageID and not payload.acceptedNameUsageID:
        raise HTTPException(status_code=400, detail="Provide either parentNameUsageID (a new taxon in the hierarchy) or acceptedNameUsageID (a new synonym of an existing taxon)")
    if payload.parentNameUsageID and payload.acceptedNameUsageID:
        raise HTTPException(status_code=400, detail="Provide parentNameUsageID OR acceptedNameUsageID, not both")
    if not payload.scientificName.strip():
        raise HTTPException(status_code=400, detail="scientificName is required")
    if payload.taxonomicStatus and payload.taxonomicStatus not in VALID_TAXONOMIC_STATUSES:
        raise HTTPException(status_code=400, detail=f"taxonomicStatus must be one of {sorted(VALID_TAXONOMIC_STATUSES)}")
    if payload.nomenclaturalStatus and payload.nomenclaturalStatus not in VALID_NOMENCLATURAL_STATUSES:
        raise HTTPException(status_code=400, detail=f"nomenclaturalStatus must be one of {sorted(VALID_NOMENCLATURAL_STATUSES)}")
    for link in (payload.literature_links or []):
        if link.Type not in VALID_TAXON_LITERATURE_TYPES:
            raise HTTPException(status_code=400, detail=f"Literature link Type must be one of {sorted(VALID_TAXON_LITERATURE_TYPES)}")

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if payload.parentNameUsageID:
            cursor.execute('SELECT "taxonID", "acceptedNameUsageID" FROM taxonomy WHERE "taxonID" = %s;', (payload.parentNameUsageID,))
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=400, detail="parentNameUsageID does not match any taxon")
            if row["acceptedNameUsageID"] is not None:
                raise HTTPException(status_code=400, detail="Cannot set the parent to a taxon that is itself a synonym - point to its accepted name instead")
        if payload.acceptedNameUsageID:
            cursor.execute('SELECT "taxonID", "acceptedNameUsageID" FROM taxonomy WHERE "taxonID" = %s;', (payload.acceptedNameUsageID,))
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=400, detail="acceptedNameUsageID does not match any taxon")
            if row["acceptedNameUsageID"] is not None:
                raise HTTPException(status_code=400, detail="Cannot mark this as a synonym of another synonym - point to the accepted name directly")

        cursor.execute("SELECT nextval('web_taxonid_seq');")
        new_id = f"WEB-{cursor.fetchone()['nextval']}"

        cursor.execute("""
            INSERT INTO taxonomy (
                "taxonID", "scientificName", "scientificnameAuthorship", "taxonrank",
                "taxonomicStatus", "nomenclaturalStatus", "taxonRemarks",
                "parentNameUsageID", "acceptedNameUsageID"
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
        """, (
            new_id, payload.scientificName.strip(), payload.scientificnameAuthorship, payload.taxonrank,
            payload.taxonomicStatus, payload.nomenclaturalStatus, payload.taxonRemarks,
            payload.parentNameUsageID, payload.acceptedNameUsageID
        ))

        log_snapshot = payload.dict(exclude={"notes", "literature_links"})
        cursor.execute("""
            INSERT INTO admin_activity_log (performed_by_user_id, action_type, table_name, record_id, field_changes, notes)
            VALUES (%s, %s, %s, %s, %s::jsonb, %s);
        """, (user["user_id"], "taxonomy_create", "taxonomy", new_id, json.dumps(log_snapshot), payload.notes))

        linked_lit_ids = []
        for link in (payload.literature_links or []):
            cursor.execute('SELECT 1 FROM literature WHERE "litID" = %s;', (link.litID,))
            if not cursor.fetchone():
                raise HTTPException(status_code=400, detail=f"No literature entry found with litID {link.litID}")
            cursor.execute("""
                INSERT INTO taxonomy_literature_junction (
                    taxonid, "Type", "litID", is_identification_key, key_scope_rank, online_resource_url, access_notes
                ) VALUES (%s, %s, %s, %s, %s, %s, %s);
            """, (
                new_id, link.Type, link.litID, (link.Type == "Identification Key"),
                link.key_scope_rank, link.online_resource_url, link.access_notes
            ))
            cursor.execute("""
                INSERT INTO admin_activity_log (performed_by_user_id, action_type, table_name, record_id, field_changes, notes)
                VALUES (%s, %s, %s, %s, %s::jsonb, %s);
            """, (
                user["user_id"], "taxonomy_literature_link_added", "taxonomy_literature_junction", new_id,
                json.dumps({"litID": link.litID, "Type": link.Type}), link.notes
            ))
            linked_lit_ids.append(link.litID)

        conn.commit()
        return {"taxonID": new_id, "message": "Taxon created.", "linked_literature": linked_lit_ids}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Could not create taxon: {str(e)}")
    finally:
        cursor.close()
        conn.close()


# ----------------------------------------------------------------
# Taxon <-> literature linking (taxonomy_literature_junction)
# ----------------------------------------------------------------

@app.get("/api/v1/admin/taxonomy/{taxon_id}/literature-links")
def get_taxon_literature_links(taxon_id: str, user: dict = Depends(require_superuser)):
    """
    Returns every literature link on a taxon in full, unformatted
    detail - unlike the public /api/v1/taxonomy/literature/{taxon_id}
    endpoint (which only returns citations pre-grouped for display),
    this includes litID and the identification-key fields, so the
    taxonomy editor can list and remove individual links.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT
                j.taxonid, j."Type", j."litID",
                j.is_identification_key, j.key_scope_rank, j.online_resource_url, j.access_notes,
                CONCAT_WS(', ', l."authorName", l."yearPublished", l."articleTitle", l."publicationTitle") AS formatted_ref
            FROM taxonomy_literature_junction j
            JOIN literature l ON j."litID" = l."litID"
            WHERE j.taxonid = %s
            ORDER BY j."Type", l."yearPublished" DESC;
        """, (taxon_id,))
        rows = cursor.fetchall()
        return {"taxon_id": taxon_id, "count": len(rows), "links": rows}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query error: {str(e)}")
    finally:
        cursor.close()
        conn.close()


@app.post("/api/v1/admin/taxonomy/{taxon_id}/literature-links")
def add_taxon_literature_link(
    taxon_id: str,
    payload: TaxonLiteratureLinkSubmission,
    user: dict = Depends(require_superuser)
):
    """
    Links a literature reference to a taxon, recording which of the
    five relationship types it represents (the same categories the
    public taxonomy page groups citations into) - including
    "Identification Key" as its own type, distinct from taxonomic/
    synonymy decisions - and, when that's the type chosen, optionally
    the rank the key covers. Logged to admin_activity_log like every
    other taxonomy edit.
    """
    if payload.Type not in VALID_TAXON_LITERATURE_TYPES:
        raise HTTPException(status_code=400, detail=f"Type must be one of {sorted(VALID_TAXON_LITERATURE_TYPES)}")

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT 1 FROM taxonomy WHERE "taxonID" = %s;', (taxon_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail=f"No taxon found with taxonID {taxon_id}")
        cursor.execute('SELECT 1 FROM literature WHERE "litID" = %s;', (payload.litID,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail=f"No literature entry found with litID {payload.litID}")

        cursor.execute("""
            SELECT 1 FROM taxonomy_literature_junction
            WHERE taxonid = %s AND "Type" = %s AND "litID" = %s;
        """, (taxon_id, payload.Type, payload.litID))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="This taxon is already linked to that reference with that relationship type")

        cursor.execute("""
            INSERT INTO taxonomy_literature_junction (
                taxonid, "Type", "litID", is_identification_key, key_scope_rank, online_resource_url, access_notes
            ) VALUES (%s, %s, %s, %s, %s, %s, %s);
        """, (
            taxon_id, payload.Type, payload.litID, (payload.Type == "Identification Key"),
            payload.key_scope_rank, payload.online_resource_url, payload.access_notes
        ))

        cursor.execute("""
            INSERT INTO admin_activity_log (performed_by_user_id, action_type, table_name, record_id, field_changes, notes)
            VALUES (%s, %s, %s, %s, %s::jsonb, %s);
        """, (
            user["user_id"], "taxonomy_literature_link_added", "taxonomy_literature_junction", taxon_id,
            json.dumps({"litID": payload.litID, "Type": payload.Type}), payload.notes
        ))

        conn.commit()
        return {"message": "Literature link added.", "taxon_id": taxon_id, "litID": payload.litID, "Type": payload.Type}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Could not add literature link: {str(e)}")
    finally:
        cursor.close()
        conn.close()


@app.delete("/api/v1/admin/taxonomy/{taxon_id}/literature-links")
def remove_taxon_literature_link(
    taxon_id: str,
    lit_id: str = Query(..., description="The litID to unlink"),
    link_type: str = Query(..., alias="type", description="The relationship type of the link being removed"),
    user: dict = Depends(require_superuser)
):
    """
    Removes one taxon-literature link, identified by its composite
    key (taxon, reference, relationship type), since the junction
    table has no separate surrogate ID column of its own.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            DELETE FROM taxonomy_literature_junction
            WHERE taxonid = %s AND "Type" = %s AND "litID" = %s;
        """, (taxon_id, link_type, lit_id))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="No matching literature link found to remove")

        cursor.execute("""
            INSERT INTO admin_activity_log (performed_by_user_id, action_type, table_name, record_id, field_changes, notes)
            VALUES (%s, %s, %s, %s, %s::jsonb, %s);
        """, (
            user["user_id"], "taxonomy_literature_link_removed", "taxonomy_literature_junction", taxon_id,
            json.dumps({"litID": lit_id, "Type": link_type}), None
        ))

        conn.commit()
        return {"message": "Literature link removed."}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Could not remove literature link: {str(e)}")
    finally:
        cursor.close()
        conn.close()


@app.get("/api/v1/admin/activity-log")
def get_admin_activity_log(
    table_name: Optional[str] = Query(None, description="Filter to one table, e.g. 'taxonomy'"),
    record_id: Optional[str] = Query(None, description="Filter to one record's full edit history"),
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(require_superuser)
):
    """
    Returns admin activity log entries, most recent first. Used both
    as a general recent-changes feed, and (filtered by record_id) as
    the edit-history panel on a single taxon's editor page.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        where_clauses = []
        params = []
        if table_name:
            where_clauses.append("l.table_name = %s")
            params.append(table_name)
        if record_id:
            where_clauses.append("l.record_id = %s")
            params.append(record_id)
        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        cursor.execute(f"""
            SELECT l.log_id, l.performed_by_user_id, u.display_name AS performed_by_name,
                   l.action_type, l.table_name, l.record_id, l.field_changes, l.notes, l.performed_at
            FROM admin_activity_log l
            LEFT JOIN users u ON l.performed_by_user_id = u.user_id
            {where_sql}
            ORDER BY l.performed_at DESC
            LIMIT %s;
        """, params + [limit])
        rows = cursor.fetchall()
        return {"count": len(rows), "entries": rows}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query error: {str(e)}")
    finally:
        cursor.close()
        conn.close()


# ==========================================================
# RECORD EDITOR (samples / observations / demographics /
# specimens) - superuser only
# ==========================================================
# Lets a superuser correct, extend, delete, or duplicate the actual
# field records - as opposed to the taxonomy/literature reference
# data the admin tools above manage. Every write here follows the
# same pattern already established elsewhere: full-replace edits
# with a logged diff, cascading deletes made explicit and safe
# rather than left to chance or a database default, and duplication
# as a first-class operation (e.g. splitting one sample/observation
# that actually spans more than one microhabitat into two).
#
# verification_status/verified_by/verified_date/verification_notes
# on observations are deliberately NOT editable through this editor -
# they're managed through the audited /review workflow
# (submit_verification_action above) so every change to them keeps
# landing in observation_verification_actions.

def _log_admin_action(cursor, user, action_type, table_name, record_id, field_changes, notes=None):
    cursor.execute("""
        INSERT INTO admin_activity_log (performed_by_user_id, action_type, table_name, record_id, field_changes, notes)
        VALUES (%s, %s, %s, %s, %s::jsonb, %s);
    """, (user["user_id"], action_type, table_name, record_id, json.dumps(field_changes), notes))


def _diff_row(current, new_values: dict):
    """
    Field-by-field diff for full-replace edits. Empty string and None
    are treated as equivalent for text fields (matching the taxonomy
    editor's convention), but non-string values (numbers, booleans)
    are compared directly, so a legitimate 0 or False is never
    mistaken for "unset".
    """
    changes = {}
    for field, new_val in new_values.items():
        old_val = current[field]
        old_norm = (old_val or None) if isinstance(old_val, str) or old_val is None else old_val
        new_norm = (new_val or None) if isinstance(new_val, str) or new_val is None else new_val
        if old_norm != new_norm:
            changes[field] = {"old": old_val, "new": new_val}
    return changes


# ---------- samples ----------

@app.get("/api/v1/admin/samples/search")
def admin_search_samples(
    q: str = Query(..., min_length=2),
    limit: int = Query(20, ge=1, le=50),
    user: dict = Depends(require_superuser)
):
    """
    Simple ILIKE search across eventID, samplingLocation, recordedBy
    and gridRef - for finding a sample to edit without already
    knowing its exact eventID.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        like = f"%{q}%"
        cursor.execute("""
            SELECT "eventID", "samplingLocation", "recordedBy", "gridRef",
                   "earliestDateCollected", "latestDateCollected"
            FROM samples
            WHERE "eventID" ILIKE %s OR "samplingLocation" ILIKE %s OR "recordedBy" ILIKE %s OR "gridRef" ILIKE %s
            ORDER BY "earliestDateCollected" DESC NULLS LAST
            LIMIT %s;
        """, (like, like, like, like, limit))
        return {"results": cursor.fetchall()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query error: {str(e)}")
    finally:
        cursor.close()
        conn.close()


@app.get("/api/v1/admin/samples/{event_id}")
def get_admin_sample_detail(event_id: str, user: dict = Depends(require_superuser)):
    """
    Full sample record plus the observations attached to it (with
    taxon name and verification status, so you can see and jump into
    each one), and its literature/project source links.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT * FROM samples WHERE "eventID" = %s;', (event_id,))
        sample = cursor.fetchone()
        if not sample:
            raise HTTPException(status_code=404, detail=f"No sample found with eventID {event_id}")

        cursor.execute("""
            SELECT o."observationID", o."taxonID", t."scientificName" AS taxon_name, o.verification_status
            FROM observations o
            LEFT JOIN taxonomy t ON o."taxonID" = t."taxonID"
            WHERE o."eventID" = %s
            ORDER BY t."scientificName";
        """, (event_id,))
        observations = cursor.fetchall()

        cursor.execute("""
            SELECT j."Type" AS type, j."litID" AS lit_id,
                   CONCAT_WS(', ', l."authorName", l."yearPublished", l."articleTitle", l."publicationTitle") AS formatted_ref
            FROM sample_literature_junction j
            JOIN literature l ON j."litID" = l."litID"
            WHERE j."eventID" = %s;
        """, (event_id,))
        literature_links = cursor.fetchall()

        cursor.execute("""
            SELECT j.type, j.project_id, p.project_name
            FROM sample_project_junction j
            JOIN recording_projects p ON j.project_id = p.project_id
            WHERE j."eventID" = %s;
        """, (event_id,))
        project_links = cursor.fetchall()

        return {
            "sample": sample,
            "observations": observations,
            "literature_links": literature_links,
            "project_links": project_links
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query error: {str(e)}")
    finally:
        cursor.close()
        conn.close()


@app.put("/api/v1/admin/samples/{event_id}")
def edit_sample(event_id: str, payload: SampleEditSubmission, user: dict = Depends(require_superuser)):
    """
    Full-replace edit of a sample's fields. If the coordinates
    change, geom_wgs84 is rebuilt to match (or cleared if coordinates
    are removed) - the same way it's built at submission time - so it
    never goes silently stale.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT * FROM samples WHERE "eventID" = %s;', (event_id,))
        current = cursor.fetchone()
        if not current:
            raise HTTPException(status_code=404, detail=f"No sample found with eventID {event_id}")

        new_values = {
            "samplingLocation": payload.samplingLocation,
            "decimalLatitude": payload.decimalLatitude,
            "decimalLongitude": payload.decimalLongitude,
            "coordinateuncertaintyinmeters": payload.coordinateuncertaintyinmeters,
            "bngx": payload.bngx,
            "bngy": payload.bngy,
            "gridRef": payload.gridRef,
            "earliestDateCollected": payload.earliestDateCollected,
            "latestDateCollected": payload.latestDateCollected,
            "habitat": payload.habitat,
            "microhabitat": payload.microhabitat,
            "SHADe": payload.SHADe,
            "samplingProtocol": payload.samplingProtocol,
            "samplesizeValue": payload.samplesizeValue,
            "samplesizeUnit": payload.samplesizeUnit,
            "recordedBy": payload.recordedBy,
            "eventRemarks": payload.eventRemarks,
            "datarestricted": payload.datarestricted,
            "licenceHolder": payload.licenceHolder,
            "dataSource[free text]": payload.dataSource,
        }

        field_changes = _diff_row(current, new_values)
        if not field_changes:
            return {"eventID": event_id, "message": "No changes to save.", "changed_fields": []}

        cursor.execute("""
            UPDATE samples SET
                "samplingLocation" = %s, "decimalLatitude" = %s, "decimalLongitude" = %s,
                "coordinateuncertaintyinmeters" = %s, "bngx" = %s, "bngy" = %s, "gridRef" = %s,
                "earliestDateCollected" = %s, "latestDateCollected" = %s, "habitat" = %s,
                "microhabitat" = %s, "SHADe" = %s, "samplingProtocol" = %s,
                "samplesizeValue" = %s, "samplesizeUnit" = %s, "recordedBy" = %s, "eventRemarks" = %s,
                "datarestricted" = %s, "licenceHolder" = %s, "dataSource[free text]" = %s
            WHERE "eventID" = %s;
        """, (
            new_values["samplingLocation"], new_values["decimalLatitude"], new_values["decimalLongitude"],
            new_values["coordinateuncertaintyinmeters"], new_values["bngx"], new_values["bngy"], new_values["gridRef"],
            new_values["earliestDateCollected"], new_values["latestDateCollected"], new_values["habitat"],
            new_values["microhabitat"], new_values["SHADe"], new_values["samplingProtocol"],
            new_values["samplesizeValue"], new_values["samplesizeUnit"], new_values["recordedBy"], new_values["eventRemarks"],
            new_values["datarestricted"], new_values["licenceHolder"], new_values["dataSource[free text]"],
            event_id
        ))

        if "decimalLatitude" in field_changes or "decimalLongitude" in field_changes:
            if new_values["decimalLatitude"] is not None and new_values["decimalLongitude"] is not None:
                cursor.execute("""
                    UPDATE samples SET geom_wgs84 = ST_SetSRID(ST_MakePoint(%s::float8, %s::float8), 4326)
                    WHERE "eventID" = %s;
                """, (new_values["decimalLongitude"], new_values["decimalLatitude"], event_id))
            else:
                cursor.execute('UPDATE samples SET geom_wgs84 = NULL WHERE "eventID" = %s;', (event_id,))

        _log_admin_action(cursor, user, "sample_edit", "samples", event_id, field_changes, payload.notes)
        conn.commit()
        return {"eventID": event_id, "message": "Saved.", "changed_fields": list(field_changes.keys())}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Could not save sample: {str(e)}")
    finally:
        cursor.close()
        conn.close()


@app.get("/api/v1/admin/samples/{event_id}/delete-preview")
def preview_sample_delete(event_id: str, user: dict = Depends(require_superuser)):
    """
    Samples don't cascade-delete their observations - an observation
    is a real scientific record in its own right, so it must be moved
    or deleted individually first. This tells the confirmation
    exactly what's blocking deletion.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT 1 FROM samples WHERE "eventID" = %s;', (event_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail=f"No sample found with eventID {event_id}")
        cursor.execute('SELECT COUNT(*) AS n FROM observations WHERE "eventID" = %s;', (event_id,))
        obs_count = cursor.fetchone()["n"]
        return {"observations": obs_count, "can_delete": obs_count == 0}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query error: {str(e)}")
    finally:
        cursor.close()
        conn.close()


@app.delete("/api/v1/admin/samples/{event_id}")
def delete_sample(event_id: str, user: dict = Depends(require_superuser)):
    """
    Deletes a sample. Blocked while any observations still reference
    it; its own literature/project source links are cleaned up
    automatically since nothing else depends on them.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT 1 FROM samples WHERE "eventID" = %s;', (event_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail=f"No sample found with eventID {event_id}")
        cursor.execute('SELECT COUNT(*) AS n FROM observations WHERE "eventID" = %s;', (event_id,))
        obs_count = cursor.fetchone()["n"]
        if obs_count:
            raise HTTPException(status_code=400, detail=f"Cannot delete - {obs_count} observation(s) still belong to this sample. Move or delete those first.")

        cursor.execute('DELETE FROM sample_literature_junction WHERE "eventID" = %s;', (event_id,))
        cursor.execute('DELETE FROM sample_project_junction WHERE "eventID" = %s;', (event_id,))
        cursor.execute('DELETE FROM samples WHERE "eventID" = %s;', (event_id,))

        _log_admin_action(cursor, user, "sample_delete", "samples", event_id, {})
        conn.commit()
        return {"message": "Sample deleted."}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Could not delete sample: {str(e)}")
    finally:
        cursor.close()
        conn.close()


@app.post("/api/v1/admin/samples/{event_id}/duplicate")
def duplicate_sample(event_id: str, payload: SampleDuplicateSubmission, user: dict = Depends(require_superuser)):
    """
    Creates a new sample with the same field values (a fresh
    WEB-prefixed eventID, fresh submitted_by/entered_by/entered_at) -
    typically used to split one over-broad sample into several, one
    per microhabitat, before editing each copy's microhabitat field
    and moving or duplicating the relevant observations onto it. Does
    not copy observations, literature links, or project links - those
    are left for the superuser to attach individually to whichever
    copy they actually belong on.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT * FROM samples WHERE "eventID" = %s;', (event_id,))
        source = cursor.fetchone()
        if not source:
            raise HTTPException(status_code=404, detail=f"No sample found with eventID {event_id}")

        cursor.execute("SELECT nextval('web_eventid_seq');")
        new_id = f"WEB-{cursor.fetchone()['nextval']}"

        cursor.execute("""
            INSERT INTO samples (
                "eventID", "samplingLocation", "decimalLatitude", "decimalLongitude",
                "coordinateuncertaintyinmeters", "bngx", "bngy", "gridRef",
                "earliestDateCollected", "latestDateCollected", "habitat", "microhabitat",
                "SHADe", "samplingProtocol", "samplesizeValue", "samplesizeUnit", "recordedBy",
                "eventRemarks", "datarestricted", "licenceHolder", "dataSource[free text]",
                submitted_by_user_id, entered_by, entered_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP
            );
        """, (
            new_id, source["samplingLocation"], source["decimalLatitude"], source["decimalLongitude"],
            source["coordinateuncertaintyinmeters"], source["bngx"], source["bngy"], source["gridRef"],
            source["earliestDateCollected"], source["latestDateCollected"], source["habitat"], source["microhabitat"],
            source["SHADe"], source["samplingProtocol"], source["samplesizeValue"], source["samplesizeUnit"], source["recordedBy"],
            source["eventRemarks"], source["datarestricted"], source["licenceHolder"], source["dataSource[free text]"],
            user["user_id"], user["display_name"]
        ))

        if source["decimalLatitude"] is not None and source["decimalLongitude"] is not None:
            cursor.execute("""
                UPDATE samples SET geom_wgs84 = ST_SetSRID(ST_MakePoint(%s, %s), 4326)
                WHERE "eventID" = %s;
            """, (source["decimalLongitude"], source["decimalLatitude"], new_id))

        _log_admin_action(cursor, user, "sample_duplicate", "samples", new_id, {"duplicated_from": event_id}, payload.notes)
        conn.commit()
        return {"eventID": new_id, "message": f"Duplicated from {event_id}."}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Could not duplicate sample: {str(e)}")
    finally:
        cursor.close()
        conn.close()


@app.post("/api/v1/admin/samples/{event_id}/literature-links")
def add_sample_literature_link(event_id: str, payload: SampleLiteratureLinkSubmission, user: dict = Depends(require_superuser)):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT 1 FROM samples WHERE "eventID" = %s;', (event_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail=f"No sample found with eventID {event_id}")
        cursor.execute('SELECT 1 FROM literature WHERE "litID" = %s;', (payload.litID,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail=f"No literature entry found with litID {payload.litID}")
        cursor.execute("""
            SELECT 1 FROM sample_literature_junction WHERE "eventID" = %s AND "Type" = %s AND "litID" = %s;
        """, (event_id, payload.Type, payload.litID))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="This sample is already linked to that reference with that type")

        cursor.execute("""
            INSERT INTO sample_literature_junction ("eventID", "Type", "litID") VALUES (%s, %s, %s);
        """, (event_id, payload.Type, payload.litID))
        _log_admin_action(cursor, user, "sample_literature_link_added", "sample_literature_junction", event_id,
                           {"litID": payload.litID, "Type": payload.Type}, payload.notes)
        conn.commit()
        return {"message": "Literature link added."}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Could not add literature link: {str(e)}")
    finally:
        cursor.close()
        conn.close()


@app.delete("/api/v1/admin/samples/{event_id}/literature-links")
def remove_sample_literature_link(
    event_id: str,
    lit_id: str = Query(...),
    link_type: str = Query(..., alias="type"),
    user: dict = Depends(require_superuser)
):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            DELETE FROM sample_literature_junction WHERE "eventID" = %s AND "Type" = %s AND "litID" = %s;
        """, (event_id, link_type, lit_id))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="No matching literature link found to remove")
        _log_admin_action(cursor, user, "sample_literature_link_removed", "sample_literature_junction", event_id,
                           {"litID": lit_id, "Type": link_type})
        conn.commit()
        return {"message": "Literature link removed."}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Could not remove literature link: {str(e)}")
    finally:
        cursor.close()
        conn.close()


@app.post("/api/v1/admin/samples/{event_id}/projects")
def add_sample_project_link(event_id: str, payload: SampleProjectLinkSubmission, user: dict = Depends(require_superuser)):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT 1 FROM samples WHERE "eventID" = %s;', (event_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail=f"No sample found with eventID {event_id}")
        cursor.execute("SELECT 1 FROM recording_projects WHERE project_id = %s;", (payload.project_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail=f"No project found with id {payload.project_id}")
        cursor.execute("""
            SELECT 1 FROM sample_project_junction WHERE "eventID" = %s AND project_id = %s AND type = %s;
        """, (event_id, payload.project_id, payload.type))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="This sample is already linked to that project with that type")

        cursor.execute("""
            INSERT INTO sample_project_junction ("eventID", project_id, type) VALUES (%s, %s, %s);
        """, (event_id, payload.project_id, payload.type))
        _log_admin_action(cursor, user, "sample_project_link_added", "sample_project_junction", event_id,
                           {"project_id": payload.project_id, "type": payload.type}, payload.notes)
        conn.commit()
        return {"message": "Project link added."}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Could not add project link: {str(e)}")
    finally:
        cursor.close()
        conn.close()


@app.delete("/api/v1/admin/samples/{event_id}/projects")
def remove_sample_project_link(
    event_id: str,
    project_id: int = Query(...),
    link_type: str = Query(..., alias="type"),
    user: dict = Depends(require_superuser)
):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            DELETE FROM sample_project_junction WHERE "eventID" = %s AND project_id = %s AND type = %s;
        """, (event_id, project_id, link_type))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="No matching project link found to remove")
        _log_admin_action(cursor, user, "sample_project_link_removed", "sample_project_junction", event_id,
                           {"project_id": project_id, "type": link_type})
        conn.commit()
        return {"message": "Project link removed."}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Could not remove project link: {str(e)}")
    finally:
        cursor.close()
        conn.close()


@app.post("/api/v1/admin/samples/{event_id}/observations")
def admin_create_observation(event_id: str, payload: ObservationEditSubmission, user: dict = Depends(require_superuser)):
    """
    Superuser quick-create of a brand new observation directly under
    a sample - bypasses the ownership check the contributor-facing
    /api/v1/submit/observation enforces, since a superuser may
    legitimately be adding to someone else's sample.
    """
    if not payload.taxonID:
        raise HTTPException(status_code=400, detail="taxonID is required")
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT 1 FROM samples WHERE "eventID" = %s;', (event_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail=f"No sample found with eventID {event_id}")
        cursor.execute('SELECT 1 FROM taxonomy WHERE "taxonID" = %s;', (payload.taxonID,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail=f"No taxon found with taxonID {payload.taxonID}")

        cursor.execute("SELECT nextval('web_observationid_seq');")
        new_id = f"WEB-{cursor.fetchone()['nextval']}"

        cursor.execute("""
            INSERT INTO observations (
                "observationID", "eventID", "taxonID", "identifiedBy",
                "identificationVerificationStatus", "identificationRemarks",
                "collectionID", "catalogNumber", "basisOfRecord", "idTechnique", "litID",
                "idText[free_text]", "occurrenceRemarks", share_with_nbn, share_with_gbif,
                verification_status, submitted_by_user_id, entered_by, entered_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending', %s, %s, CURRENT_TIMESTAMP
            );
        """, (
            new_id, event_id, payload.taxonID, payload.identifiedBy,
            payload.identificationVerificationStatus, payload.identificationRemarks,
            payload.collectionID, payload.catalogNumber, payload.basisOfRecord, payload.idTechnique, payload.litID,
            payload.idText, payload.occurrenceRemarks, payload.share_with_nbn, payload.share_with_gbif,
            user["user_id"], user["display_name"]
        ))
        _log_admin_action(cursor, user, "observation_create", "observations", new_id, {"eventID": event_id, "taxonID": payload.taxonID}, payload.notes)
        conn.commit()
        return {"observationID": new_id, "message": "Observation created."}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Could not create observation: {str(e)}")
    finally:
        cursor.close()
        conn.close()


# ---------- observations ----------

@app.get("/api/v1/admin/observations")
def admin_list_observations(
    taxon_id: Optional[str] = Query(None),
    event_id: Optional[str] = Query(None),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: dict = Depends(require_superuser)
):
    """
    Lists observations filtered by taxon and/or sample - used to
    browse into a specific taxon's observations without needing to
    know an observationID up front.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        where = []
        params = []
        if taxon_id:
            where.append('o."taxonID" = %s')
            params.append(taxon_id)
        if event_id:
            where.append('o."eventID" = %s')
            params.append(event_id)
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        cursor.execute(f"""
            SELECT o."observationID", o."eventID", o."taxonID", t."scientificName" AS taxon_name,
                   o.verification_status, s."samplingLocation", s."earliestDateCollected"
            FROM observations o
            LEFT JOIN taxonomy t ON o."taxonID" = t."taxonID"
            LEFT JOIN samples s ON o."eventID" = s."eventID"
            {where_sql}
            ORDER BY s."earliestDateCollected" DESC NULLS LAST
            LIMIT %s OFFSET %s;
        """, params + [limit, offset])
        rows = cursor.fetchall()
        cursor.execute(f"SELECT COUNT(*) AS total FROM observations o {where_sql};", params)
        total = cursor.fetchone()["total"]
        return {"results": rows, "total": total, "limit": limit, "offset": offset}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query error: {str(e)}")
    finally:
        cursor.close()
        conn.close()


@app.get("/api/v1/admin/observations/{observation_id}")
def get_admin_observation_detail(observation_id: str, user: dict = Depends(require_superuser)):
    """
    Full observation record plus its sample summary, taxon name, its
    demographic groups (each with their own specimens nested inside),
    and its literature links.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT o.*, t."scientificName" AS taxon_name,
                   s."samplingLocation" AS sample_location, s."earliestDateCollected" AS sample_date
            FROM observations o
            LEFT JOIN taxonomy t ON o."taxonID" = t."taxonID"
            LEFT JOIN samples s ON o."eventID" = s."eventID"
            WHERE o."observationID" = %s;
        """, (observation_id,))
        obs = cursor.fetchone()
        if not obs:
            raise HTTPException(status_code=404, detail=f"No observation found with observationID {observation_id}")

        cursor.execute("""
            SELECT * FROM observation_demographics WHERE "observationID" = %s ORDER BY "demographicID";
        """, (observation_id,))
        demographics = cursor.fetchall()
        for d in demographics:
            cursor.execute("""
                SELECT * FROM specimens WHERE "demographicID" = %s ORDER BY "specimenID";
            """, (d["demographicID"],))
            d["specimens"] = cursor.fetchall()

        cursor.execute("""
            SELECT j.type, j."litID" AS lit_id,
                   CONCAT_WS(', ', l."authorName", l."yearPublished", l."articleTitle", l."publicationTitle") AS formatted_ref
            FROM observation_literature_junction j
            JOIN literature l ON j."litID" = l."litID"
            WHERE j."observationID" = %s;
        """, (observation_id,))
        literature_links = cursor.fetchall()

        return {"observation": obs, "demographics": demographics, "literature_links": literature_links}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query error: {str(e)}")
    finally:
        cursor.close()
        conn.close()


@app.put("/api/v1/admin/observations/{observation_id}")
def edit_observation(observation_id: str, payload: ObservationEditSubmission, user: dict = Depends(require_superuser)):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT * FROM observations WHERE "observationID" = %s;', (observation_id,))
        current = cursor.fetchone()
        if not current:
            raise HTTPException(status_code=404, detail=f"No observation found with observationID {observation_id}")

        if payload.eventID and payload.eventID != current["eventID"]:
            cursor.execute('SELECT 1 FROM samples WHERE "eventID" = %s;', (payload.eventID,))
            if not cursor.fetchone():
                raise HTTPException(status_code=400, detail="eventID does not match any sample")
        if payload.taxonID and payload.taxonID != current["taxonID"]:
            cursor.execute('SELECT 1 FROM taxonomy WHERE "taxonID" = %s;', (payload.taxonID,))
            if not cursor.fetchone():
                raise HTTPException(status_code=400, detail="taxonID does not match any taxon")
        if payload.litID:
            cursor.execute('SELECT 1 FROM literature WHERE "litID" = %s;', (payload.litID,))
            if not cursor.fetchone():
                raise HTTPException(status_code=400, detail="litID does not match any literature entry")

        new_values = {
            "eventID": payload.eventID or current["eventID"],
            "taxonID": payload.taxonID or current["taxonID"],
            "identifiedBy": payload.identifiedBy,
            "identificationVerificationStatus": payload.identificationVerificationStatus,
            "identificationRemarks": payload.identificationRemarks,
            "collectionID": payload.collectionID,
            "catalogNumber": payload.catalogNumber,
            "basisOfRecord": payload.basisOfRecord,
            "idTechnique": payload.idTechnique,
            "litID": payload.litID,
            "idText[free_text]": payload.idText,
            "occurrenceRemarks": payload.occurrenceRemarks,
            "share_with_nbn": payload.share_with_nbn,
            "share_with_gbif": payload.share_with_gbif,
        }
        # A taxon assignment resolves any pending batch-upload
        # placeholder - once taxonID is set, the proposed name has
        # served its purpose and shouldn't keep showing as unresolved.
        clears_placeholder = new_values["taxonID"] and current["proposed_taxon_name"]

        field_changes = _diff_row(current, new_values)
        if clears_placeholder:
            field_changes["proposed_taxon_name"] = {"old": current["proposed_taxon_name"], "new": None}
        if not field_changes:
            return {"observationID": observation_id, "message": "No changes to save.", "changed_fields": []}

        cursor.execute("""
            UPDATE observations SET
                "eventID" = %s, "taxonID" = %s, "identifiedBy" = %s,
                "identificationVerificationStatus" = %s, "identificationRemarks" = %s,
                "collectionID" = %s, "catalogNumber" = %s, "basisOfRecord" = %s, "idTechnique" = %s, "litID" = %s,
                "idText[free_text]" = %s, "occurrenceRemarks" = %s, share_with_nbn = %s, share_with_gbif = %s,
                proposed_taxon_name = %s
            WHERE "observationID" = %s;
        """, (
            new_values["eventID"], new_values["taxonID"], new_values["identifiedBy"],
            new_values["identificationVerificationStatus"], new_values["identificationRemarks"],
            new_values["collectionID"], new_values["catalogNumber"], new_values["basisOfRecord"], new_values["idTechnique"], new_values["litID"],
            new_values["idText[free_text]"], new_values["occurrenceRemarks"], new_values["share_with_nbn"], new_values["share_with_gbif"],
            (None if clears_placeholder else current["proposed_taxon_name"]), observation_id
        ))

        _log_admin_action(cursor, user, "observation_edit", "observations", observation_id, field_changes, payload.notes)
        conn.commit()
        return {"observationID": observation_id, "message": "Saved.", "changed_fields": list(field_changes.keys())}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Could not save observation: {str(e)}")
    finally:
        cursor.close()
        conn.close()


@app.get("/api/v1/admin/observations/{observation_id}/delete-preview")
def preview_observation_delete(observation_id: str, user: dict = Depends(require_superuser)):
    """
    Counts everything that cascades if this observation is deleted -
    demographics, their specimens (and any barcodes on those
    specimens), media at any of those levels, literature links,
    verification history, and any taxonomy override - so the
    confirmation dialog can say exactly what's about to disappear.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT 1 FROM observations WHERE "observationID" = %s;', (observation_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail=f"No observation found with observationID {observation_id}")

        cursor.execute('SELECT "demographicID" FROM observation_demographics WHERE "observationID" = %s;', (observation_id,))
        demographic_ids = [r["demographicID"] for r in cursor.fetchall()]

        specimen_count = 0
        barcode_count = 0
        if demographic_ids:
            cursor.execute('SELECT "specimenID" FROM specimens WHERE "demographicID" = ANY(%s);', (demographic_ids,))
            specimen_ids = [r["specimenID"] for r in cursor.fetchall()]
            specimen_count = len(specimen_ids)
            if specimen_ids:
                cursor.execute('SELECT COUNT(*) AS n FROM specimen_barcodes WHERE specimen_id = ANY(%s);', (specimen_ids,))
                barcode_count = cursor.fetchone()["n"]

        cursor.execute('SELECT COUNT(*) AS n FROM observation_media WHERE observation_id = %s;', (observation_id,))
        media_count = cursor.fetchone()["n"]
        cursor.execute('SELECT COUNT(*) AS n FROM observation_literature_junction WHERE "observationID" = %s;', (observation_id,))
        lit_count = cursor.fetchone()["n"]
        cursor.execute('SELECT COUNT(*) AS n FROM observation_verification_actions WHERE "observationID" = %s;', (observation_id,))
        verification_count = cursor.fetchone()["n"]

        return {
            "demographics": len(demographic_ids),
            "specimens": specimen_count,
            "specimen_barcodes": barcode_count,
            "media": media_count,
            "literature_links": lit_count,
            "verification_history": verification_count
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query error: {str(e)}")
    finally:
        cursor.close()
        conn.close()


@app.delete("/api/v1/admin/observations/{observation_id}")
def delete_observation(observation_id: str, user: dict = Depends(require_superuser)):
    """
    Deletes an observation and everything genuinely subordinate to it
    (demographics, their specimens and barcodes, media at any of
    those levels, literature links, verification history, and any
    taxonomy override) inside one transaction - all-or-nothing, so it
    can never leave orphaned demographics or specimens behind.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT 1 FROM observations WHERE "observationID" = %s;', (observation_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail=f"No observation found with observationID {observation_id}")

        cursor.execute('SELECT "demographicID" FROM observation_demographics WHERE "observationID" = %s;', (observation_id,))
        demographic_ids = [r["demographicID"] for r in cursor.fetchall()]

        if demographic_ids:
            cursor.execute('SELECT "specimenID" FROM specimens WHERE "demographicID" = ANY(%s);', (demographic_ids,))
            specimen_ids = [r["specimenID"] for r in cursor.fetchall()]
            if specimen_ids:
                cursor.execute('DELETE FROM specimen_barcodes WHERE specimen_id = ANY(%s);', (specimen_ids,))
                cursor.execute('DELETE FROM observation_media WHERE specimen_id = ANY(%s);', (specimen_ids,))
                cursor.execute('DELETE FROM specimens WHERE "specimenID" = ANY(%s);', (specimen_ids,))
            cursor.execute('DELETE FROM observation_media WHERE demographic_id = ANY(%s);', (demographic_ids,))
            cursor.execute('DELETE FROM observation_demographics WHERE "demographicID" = ANY(%s);', (demographic_ids,))

        cursor.execute('DELETE FROM observation_media WHERE observation_id = %s;', (observation_id,))
        cursor.execute('DELETE FROM observation_literature_junction WHERE "observationID" = %s;', (observation_id,))
        cursor.execute('DELETE FROM observation_verification_actions WHERE "observationID" = %s;', (observation_id,))
        cursor.execute('DELETE FROM observation_taxonomy_override WHERE observation_id = %s;', (observation_id,))
        cursor.execute('DELETE FROM observations WHERE "observationID" = %s;', (observation_id,))

        _log_admin_action(cursor, user, "observation_delete", "observations", observation_id,
                           {"demographics_deleted": len(demographic_ids)})
        conn.commit()
        return {"message": "Observation deleted."}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Could not delete observation: {str(e)}")
    finally:
        cursor.close()
        conn.close()


@app.post("/api/v1/admin/observations/{observation_id}/duplicate")
def duplicate_observation(observation_id: str, payload: ObservationDuplicateSubmission, user: dict = Depends(require_superuser)):
    """
    Creates a new observation copying this one's fields - typically
    used together with sample duplication to split a single
    over-broad record into separate ones per microhabitat (or similar
    split). new_event_id/new_taxon_id let the copy point somewhere
    different straight away; copy_demographics also deep-copies its
    demographic groups and their specimens onto the new observation.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT * FROM observations WHERE "observationID" = %s;', (observation_id,))
        source = cursor.fetchone()
        if not source:
            raise HTTPException(status_code=404, detail=f"No observation found with observationID {observation_id}")

        target_event_id = payload.new_event_id or source["eventID"]
        target_taxon_id = payload.new_taxon_id or source["taxonID"]
        cursor.execute('SELECT 1 FROM samples WHERE "eventID" = %s;', (target_event_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=400, detail="new_event_id does not match any sample")
        cursor.execute('SELECT 1 FROM taxonomy WHERE "taxonID" = %s;', (target_taxon_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=400, detail="new_taxon_id does not match any taxon")

        cursor.execute("SELECT nextval('web_observationid_seq');")
        new_id = f"WEB-{cursor.fetchone()['nextval']}"

        cursor.execute("""
            INSERT INTO observations (
                "observationID", "eventID", "taxonID", "identifiedBy",
                "identificationVerificationStatus", "identificationRemarks",
                "collectionID", "catalogNumber", "basisOfRecord", "idTechnique", "litID",
                "idText[free_text]", "occurrenceRemarks", share_with_nbn, share_with_gbif,
                verification_status, submitted_by_user_id, entered_by, entered_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending', %s, %s, CURRENT_TIMESTAMP
            );
        """, (
            new_id, target_event_id, target_taxon_id, source["identifiedBy"],
            source["identificationVerificationStatus"], source["identificationRemarks"],
            source["collectionID"], source["catalogNumber"], source["basisOfRecord"], source["idTechnique"], source["litID"],
            source["idText[free_text]"], source["occurrenceRemarks"], source["share_with_nbn"], source["share_with_gbif"],
            user["user_id"], user["display_name"]
        ))

        copied_demographics = 0
        copied_specimens = 0
        if payload.copy_demographics:
            cursor.execute('SELECT * FROM observation_demographics WHERE "observationID" = %s;', (observation_id,))
            for demo in cursor.fetchall():
                cursor.execute("SELECT nextval('web_demographicid_seq');")
                new_demo_id = f"WEB-{cursor.fetchone()['nextval']}"
                cursor.execute("""
                    INSERT INTO observation_demographics (
                        "demographicID", "observationID", sex, lifestage, count,
                        density, "densityUnit", "minCount", "maxCount", "countDescription"
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                """, (
                    new_demo_id, new_id, demo["sex"], demo["lifestage"], demo["count"],
                    demo["density"], demo["densityUnit"], demo["minCount"], demo["maxCount"], demo["countDescription"]
                ))
                copied_demographics += 1

                cursor.execute('SELECT * FROM specimens WHERE "demographicID" = %s;', (demo["demographicID"],))
                for spec in cursor.fetchall():
                    cursor.execute("SELECT nextval('web_specimenid_seq');")
                    new_spec_id = f"WEB-{cursor.fetchone()['nextval']}"
                    cursor.execute("""
                        INSERT INTO specimens (
                            "specimenID", "demographicID", "specCount", "specLocation",
                            "specRef", "specPreservation", "specType", "specComments"
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
                    """, (
                        new_spec_id, new_demo_id, spec["specCount"], spec["specLocation"],
                        spec["specRef"], spec["specPreservation"], spec["specType"], spec["specComments"]
                    ))
                    copied_specimens += 1

        _log_admin_action(cursor, user, "observation_duplicate", "observations", new_id, {
            "duplicated_from": observation_id, "eventID": target_event_id, "taxonID": target_taxon_id,
            "copied_demographics": copied_demographics, "copied_specimens": copied_specimens
        }, payload.notes)
        conn.commit()
        return {
            "observationID": new_id, "message": f"Duplicated from {observation_id}.",
            "copied_demographics": copied_demographics, "copied_specimens": copied_specimens
        }
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Could not duplicate observation: {str(e)}")
    finally:
        cursor.close()
        conn.close()


@app.post("/api/v1/admin/observations/{observation_id}/literature-links")
def add_observation_literature_link(observation_id: str, payload: ObservationLiteratureLinkSubmission, user: dict = Depends(require_superuser)):
    if payload.type not in VALID_OBSERVATION_LITERATURE_TYPES:
        raise HTTPException(status_code=400, detail=f"type must be one of {sorted(VALID_OBSERVATION_LITERATURE_TYPES)}")
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT 1 FROM observations WHERE "observationID" = %s;', (observation_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail=f"No observation found with observationID {observation_id}")
        cursor.execute('SELECT 1 FROM literature WHERE "litID" = %s;', (payload.litID,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail=f"No literature entry found with litID {payload.litID}")
        cursor.execute("""
            SELECT 1 FROM observation_literature_junction WHERE "observationID" = %s AND type = %s AND "litID" = %s;
        """, (observation_id, payload.type, payload.litID))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="This observation is already linked to that reference with that type")

        cursor.execute("""
            INSERT INTO observation_literature_junction ("observationID", type, "litID") VALUES (%s, %s, %s);
        """, (observation_id, payload.type, payload.litID))
        _log_admin_action(cursor, user, "observation_literature_link_added", "observation_literature_junction", observation_id,
                           {"litID": payload.litID, "type": payload.type}, payload.notes)
        conn.commit()
        return {"message": "Literature link added."}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Could not add literature link: {str(e)}")
    finally:
        cursor.close()
        conn.close()


@app.delete("/api/v1/admin/observations/{observation_id}/literature-links")
def remove_observation_literature_link(
    observation_id: str,
    lit_id: str = Query(...),
    link_type: str = Query(..., alias="type"),
    user: dict = Depends(require_superuser)
):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            DELETE FROM observation_literature_junction WHERE "observationID" = %s AND type = %s AND "litID" = %s;
        """, (observation_id, link_type, lit_id))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="No matching literature link found to remove")
        _log_admin_action(cursor, user, "observation_literature_link_removed", "observation_literature_junction", observation_id,
                           {"litID": lit_id, "type": link_type})
        conn.commit()
        return {"message": "Literature link removed."}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Could not remove literature link: {str(e)}")
    finally:
        cursor.close()
        conn.close()


# ---------- demographics ----------

@app.post("/api/v1/admin/observations/{observation_id}/demographics")
def admin_create_demographic(observation_id: str, payload: DemographicEditSubmission, user: dict = Depends(require_superuser)):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT 1 FROM observations WHERE "observationID" = %s;', (observation_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail=f"No observation found with observationID {observation_id}")

        cursor.execute("SELECT nextval('web_demographicid_seq');")
        new_id = f"WEB-{cursor.fetchone()['nextval']}"

        cursor.execute("""
            INSERT INTO observation_demographics (
                "demographicID", "observationID", sex, lifestage, count,
                density, "densityUnit", "minCount", "maxCount", "countDescription"
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        """, (
            new_id, observation_id, payload.sex, payload.lifestage, payload.count,
            payload.density, payload.densityUnit, payload.minCount, payload.maxCount, payload.countDescription
        ))
        _log_admin_action(cursor, user, "demographic_create", "observation_demographics", new_id, {"observationID": observation_id}, payload.notes)
        conn.commit()
        return {"demographicID": new_id, "message": "Demographic group added."}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Could not create demographic group: {str(e)}")
    finally:
        cursor.close()
        conn.close()


@app.put("/api/v1/admin/demographics/{demographic_id}")
def edit_demographic(demographic_id: str, payload: DemographicEditSubmission, user: dict = Depends(require_superuser)):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT * FROM observation_demographics WHERE "demographicID" = %s;', (demographic_id,))
        current = cursor.fetchone()
        if not current:
            raise HTTPException(status_code=404, detail=f"No demographic group found with demographicID {demographic_id}")

        new_values = {
            "sex": payload.sex, "lifestage": payload.lifestage, "count": payload.count,
            "density": payload.density, "densityUnit": payload.densityUnit,
            "minCount": payload.minCount, "maxCount": payload.maxCount, "countDescription": payload.countDescription
        }
        field_changes = _diff_row(current, new_values)
        if not field_changes:
            return {"demographicID": demographic_id, "message": "No changes to save.", "changed_fields": []}

        cursor.execute("""
            UPDATE observation_demographics SET
                sex = %s, lifestage = %s, count = %s, density = %s, "densityUnit" = %s,
                "minCount" = %s, "maxCount" = %s, "countDescription" = %s
            WHERE "demographicID" = %s;
        """, (
            new_values["sex"], new_values["lifestage"], new_values["count"], new_values["density"], new_values["densityUnit"],
            new_values["minCount"], new_values["maxCount"], new_values["countDescription"], demographic_id
        ))
        _log_admin_action(cursor, user, "demographic_edit", "observation_demographics", demographic_id, field_changes, payload.notes)
        conn.commit()
        return {"demographicID": demographic_id, "message": "Saved.", "changed_fields": list(field_changes.keys())}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Could not save demographic group: {str(e)}")
    finally:
        cursor.close()
        conn.close()


@app.delete("/api/v1/admin/demographics/{demographic_id}")
def delete_demographic(demographic_id: str, user: dict = Depends(require_superuser)):
    """
    Deletes a demographic group and its specimens (and any barcodes
    or media attached to those specimens, plus media attached to the
    demographic itself) in one transaction.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT 1 FROM observation_demographics WHERE "demographicID" = %s;', (demographic_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail=f"No demographic group found with demographicID {demographic_id}")

        cursor.execute('SELECT "specimenID" FROM specimens WHERE "demographicID" = %s;', (demographic_id,))
        specimen_ids = [r["specimenID"] for r in cursor.fetchall()]
        if specimen_ids:
            cursor.execute('DELETE FROM specimen_barcodes WHERE specimen_id = ANY(%s);', (specimen_ids,))
            cursor.execute('DELETE FROM observation_media WHERE specimen_id = ANY(%s);', (specimen_ids,))
            cursor.execute('DELETE FROM specimens WHERE "specimenID" = ANY(%s);', (specimen_ids,))
        cursor.execute('DELETE FROM observation_media WHERE demographic_id = %s;', (demographic_id,))
        cursor.execute('DELETE FROM observation_demographics WHERE "demographicID" = %s;', (demographic_id,))

        _log_admin_action(cursor, user, "demographic_delete", "observation_demographics", demographic_id,
                           {"specimens_deleted": len(specimen_ids)})
        conn.commit()
        return {"message": "Demographic group deleted."}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Could not delete demographic group: {str(e)}")
    finally:
        cursor.close()
        conn.close()


# ---------- specimens ----------

@app.post("/api/v1/admin/demographics/{demographic_id}/specimens")
def admin_create_specimen(demographic_id: str, payload: SpecimenEditSubmission, user: dict = Depends(require_superuser)):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT 1 FROM observation_demographics WHERE "demographicID" = %s;', (demographic_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail=f"No demographic group found with demographicID {demographic_id}")

        cursor.execute("SELECT nextval('web_specimenid_seq');")
        new_id = f"WEB-{cursor.fetchone()['nextval']}"

        cursor.execute("""
            INSERT INTO specimens (
                "specimenID", "demographicID", "specCount", "specLocation",
                "specRef", "specPreservation", "specType", "specComments"
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
        """, (
            new_id, demographic_id, payload.specCount, payload.specLocation,
            payload.specRef, payload.specPreservation, payload.specType, payload.specComments
        ))
        _log_admin_action(cursor, user, "specimen_create", "specimens", new_id, {"demographicID": demographic_id}, payload.notes)
        conn.commit()
        return {"specimenID": new_id, "message": "Specimen added."}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Could not create specimen: {str(e)}")
    finally:
        cursor.close()
        conn.close()


@app.put("/api/v1/admin/specimens/{specimen_id}")
def edit_specimen(specimen_id: str, payload: SpecimenEditSubmission, user: dict = Depends(require_superuser)):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT * FROM specimens WHERE "specimenID" = %s;', (specimen_id,))
        current = cursor.fetchone()
        if not current:
            raise HTTPException(status_code=404, detail=f"No specimen found with specimenID {specimen_id}")

        new_values = {
            "specCount": payload.specCount, "specLocation": payload.specLocation, "specRef": payload.specRef,
            "specPreservation": payload.specPreservation, "specType": payload.specType, "specComments": payload.specComments
        }
        field_changes = _diff_row(current, new_values)
        if not field_changes:
            return {"specimenID": specimen_id, "message": "No changes to save.", "changed_fields": []}

        cursor.execute("""
            UPDATE specimens SET
                "specCount" = %s, "specLocation" = %s, "specRef" = %s,
                "specPreservation" = %s, "specType" = %s, "specComments" = %s
            WHERE "specimenID" = %s;
        """, (
            new_values["specCount"], new_values["specLocation"], new_values["specRef"],
            new_values["specPreservation"], new_values["specType"], new_values["specComments"], specimen_id
        ))
        _log_admin_action(cursor, user, "specimen_edit", "specimens", specimen_id, field_changes, payload.notes)
        conn.commit()
        return {"specimenID": specimen_id, "message": "Saved.", "changed_fields": list(field_changes.keys())}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Could not save specimen: {str(e)}")
    finally:
        cursor.close()
        conn.close()


@app.delete("/api/v1/admin/specimens/{specimen_id}")
def delete_specimen(specimen_id: str, user: dict = Depends(require_superuser)):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT 1 FROM specimens WHERE "specimenID" = %s;', (specimen_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail=f"No specimen found with specimenID {specimen_id}")

        cursor.execute('DELETE FROM specimen_barcodes WHERE specimen_id = %s;', (specimen_id,))
        cursor.execute('DELETE FROM observation_media WHERE specimen_id = %s;', (specimen_id,))
        cursor.execute('DELETE FROM specimens WHERE "specimenID" = %s;', (specimen_id,))

        _log_admin_action(cursor, user, "specimen_delete", "specimens", specimen_id, {})
        conn.commit()
        return {"message": "Specimen deleted."}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Could not delete specimen: {str(e)}")
    finally:
        cursor.close()
        conn.close()


# ==========================================================
# SCHEMA VIEWER (superuser only)
# ==========================================================
# This reads the database's ACTUAL live structure every time it's
# called - it never relies on any written record of the schema, so
# it can never go stale the way a document or a person's memory can.
# This exists because several migrations have been applied piecemeal
# over time (column type fixes, added override tables, etc.) and it's
# become hard to know the current real structure without querying
# pgAdmin directly. Now that's available in the browser instead.

@app.get("/api/v1/admin/schema")
def get_live_schema(user: dict = Depends(require_superuser)):
    """
    Returns every table in the public schema, each with its columns
    (name, type, nullable, default) and its foreign key relationships,
    read live from information_schema and pg_catalog. Superuser only.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            ORDER BY table_name;
        """)
        table_names = [row["table_name"] for row in cursor.fetchall()]

        cursor.execute("""
            SELECT table_name, column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = 'public'
            ORDER BY table_name, ordinal_position;
        """)
        columns_by_table = {}
        for row in cursor.fetchall():
            columns_by_table.setdefault(row["table_name"], []).append({
                "column_name": row["column_name"],
                "data_type": row["data_type"],
                "is_nullable": row["is_nullable"],
                "column_default": row["column_default"],
            })

        # Foreign keys - which column in which table points at which
        # other table/column. This is what actually shows how the
        # tables link together, which is the main thing that's hard
        # to reconstruct from memory once things have grown organically.
        cursor.execute("""
            SELECT
                tc.table_name AS from_table,
                kcu.column_name AS from_column,
                ccu.table_name AS to_table,
                ccu.column_name AS to_column
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage ccu
                ON tc.constraint_name = ccu.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public'
            ORDER BY from_table, from_column;
        """)
        foreign_keys_by_table = {}
        for row in cursor.fetchall():
            foreign_keys_by_table.setdefault(row["from_table"], []).append({
                "from_column": row["from_column"],
                "to_table": row["to_table"],
                "to_column": row["to_column"],
            })

        # Views too - these matter a lot in this project
        # (view_effective_observations, view_media_with_resolved_taxon)
        # and are otherwise invisible to a schema-only column listing.
        cursor.execute("""
            SELECT table_name AS view_name
            FROM information_schema.views
            WHERE table_schema = 'public'
            ORDER BY table_name;
        """)
        view_names = [row["view_name"] for row in cursor.fetchall()]

        tables = []
        for name in table_names:
            tables.append({
                "table_name": name,
                "columns": columns_by_table.get(name, []),
                "foreign_keys": foreign_keys_by_table.get(name, []),
                "row_count_estimate": None,  # left for a future pass if useful
            })

        return {"tables": tables, "views": view_names}
    finally:
        cursor.close()
        conn.close()

