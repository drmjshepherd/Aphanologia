from fastapi import FastAPI, HTTPException, Query, Path, Depends
from fastapi.responses import FileResponse
from typing import Optional
from database import get_db_connection
import json
import re
import os
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
    only be available to Matthew and other trusted admins - e.g. the
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

@app.get("/schema", response_class=FileResponse)
def serve_schema_viewer():
    return FileResponse("schema.html")

@app.get("/review", response_class=FileResponse)
def serve_review():
    return FileResponse("review.html")

@app.get("/admin/taxonomy", response_class=FileResponse)
def serve_taxonomy_editor():
    return FileResponse("taxonomy_editor.html")


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
    limit: int = Query(25, ge=1, le=50, description="Maximum number of matches to return")
):
    """
    Searches every taxon name in the database in one go - accepted
    names, doubtful names, misapplied names, and synonyms all live
    in the same taxonomy table, so this naturally covers all of them.

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
    presence in UK from), each formatted as a single readable citation
    string with a clickable link where sourceURL is available.
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
            "Presence in UK from": []
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
MEDIA_ROOT = r"C:\path\to\folder\Mesofauna Image Archive"

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

        if taxon_id and taxon_id.strip():
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
    recordedBy: Optional[str] = None
    eventRemarks: Optional[str] = None

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


class TaxonomyCreateSubmission(BaseModel):
    scientificName: str
    scientificnameAuthorship: Optional[str] = None
    taxonrank: str
    taxonomicStatus: Optional[str] = "accepted"
    nomenclaturalStatus: Optional[str] = None
    taxonRemarks: Optional[str] = None
    parentNameUsageID: Optional[str] = None    # set this for a new taxon in the hierarchy
    acceptedNameUsageID: Optional[str] = None  # OR set this for a new synonym of an existing taxon (not both)
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
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT nextval('web_eventid_seq');")
        new_id = f"WEB-{cursor.fetchone()['nextval']}"

        # Compose the dataSource[free text] summary. Historic rows in
        # this column hold plain descriptive text (e.g. "Matthew
        # Shepherd personal collection") - new rows follow the same
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

        cursor.execute("""
            INSERT INTO samples (
                "eventID", "samplingLocation", "decimalLatitude", "decimalLongitude",
                "coordinateuncertaintyinmeters", "earliestDateCollected", "latestDateCollected",
                "habitat", "microhabitat", "SHADe", "samplingProtocol", "recordedBy", "eventRemarks",
                "dataSource[free text]",
                submitted_by_user_id, entered_by, entered_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP
            );
        """, (
            new_id, payload.samplingLocation, payload.decimalLatitude, payload.decimalLongitude,
            payload.coordinateUncertaintyInMeters, payload.earliestDateCollected, payload.latestDateCollected,
            payload.habitat, payload.microhabitat, payload.SHADe, payload.samplingProtocol, payload.recordedBy, payload.eventRemarks,
            data_source_summary,
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
                o."observationID", o."eventID", o."taxonID", t."scientificName",
                o."identifiedBy", o."identificationVerificationStatus", o."identificationRemarks",
                o."basisOfRecord", o."idTechnique", o."idText[free_text]" AS "idText",
                o.verification_status, o.entered_at,
                u.display_name AS submitted_by_name, u.email AS submitted_by_email
            FROM observations o
            JOIN taxonomy t ON o."taxonID" = t."taxonID"
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
    directly at a genuinely accepted taxon (never at another synonym,
    and never at a taxon that still has its own children hanging off
    it in the hierarchy). Logs a field-by-field diff of whatever
    actually changed to admin_activity_log.
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

        # --- Synonymy validation ---
        new_accepted = new_values["acceptedNameUsageID"]
        if new_accepted and new_accepted != current["acceptedNameUsageID"]:
            if new_accepted == taxon_id:
                raise HTTPException(status_code=400, detail="A taxon cannot be a synonym of itself")
            cursor.execute('SELECT "taxonID", "acceptedNameUsageID" FROM taxonomy WHERE "taxonID" = %s;', (new_accepted,))
            accepted_row = cursor.fetchone()
            if not accepted_row:
                raise HTTPException(status_code=400, detail="acceptedNameUsageID does not match any taxon")
            if accepted_row["acceptedNameUsageID"] is not None:
                raise HTTPException(status_code=400, detail="Cannot mark this as a synonym of another synonym - point to the accepted name directly")
            cursor.execute('SELECT 1 FROM taxonomy WHERE "parentNameUsageID" = %s LIMIT 1;', (taxon_id,))
            if cursor.fetchone():
                raise HTTPException(status_code=400, detail="This taxon still has children in the hierarchy - reparent them elsewhere before marking it as a synonym")

        # --- Diff against current values, for the audit log ---
        field_changes = {}
        for field, new_val in new_values.items():
            if (current[field] or None) != (new_val or None):
                field_changes[field] = {"old": current[field], "new": new_val}

        if not field_changes:
            return {"taxonID": taxon_id, "message": "No changes to save.", "changed_fields": []}

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
        return {"taxonID": taxon_id, "message": "Saved.", "changed_fields": list(field_changes.keys())}
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
    """
    if not payload.parentNameUsageID and not payload.acceptedNameUsageID:
        raise HTTPException(status_code=400, detail="Provide either parentNameUsageID (a new taxon in the hierarchy) or acceptedNameUsageID (a new synonym of an existing taxon)")
    if payload.parentNameUsageID and payload.acceptedNameUsageID:
        raise HTTPException(status_code=400, detail="Provide parentNameUsageID OR acceptedNameUsageID, not both")
    if not payload.scientificName.strip():
        raise HTTPException(status_code=400, detail="scientificName is required")

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

        log_snapshot = payload.dict(exclude={"notes"})
        cursor.execute("""
            INSERT INTO admin_activity_log (performed_by_user_id, action_type, table_name, record_id, field_changes, notes)
            VALUES (%s, %s, %s, %s, %s::jsonb, %s);
        """, (user["user_id"], "taxonomy_create", "taxonomy", new_id, json.dumps(log_snapshot), payload.notes))

        conn.commit()
        return {"taxonID": new_id, "message": "Taxon created."}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Could not create taxon: {str(e)}")
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

