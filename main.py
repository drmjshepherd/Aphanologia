from fastapi import FastAPI, HTTPException, Query, Path
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

@app.get("/", response_class=FileResponse)
def serve_landing():
    return FileResponse("landing.html")

@app.get("/map", response_class=FileResponse)
def serve_map():
    return FileResponse("index.html")

@app.get("/taxonomy", response_class=FileResponse)
def serve_taxonomy():
    return FileResponse("taxonomy.html")

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
    limit: int = Query(15, ge=1, le=50, description="Maximum number of matches to return")
):
    """
    Searches every taxon name in the database in one go - accepted
    names, doubtful names, misapplied names, and synonyms all live
    in the same taxonomy table, so this naturally covers all of them
    (aim iv in the project README: 'searchable using boolean
    searches, which will link to any taxonomic entry, accepted or
    not').

    Basic boolean support: the query is split on the word 'OR' into
    separate alternative searches; within each, every space-separated
    word must appear somewhere in the name (an implicit AND).
    e.g. "carabodes minusculus" finds names containing both words;
    "carabodes OR chamobates" finds names matching either.
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

        where_sql = " OR ".join(group_clauses)

        sql = f"""
            SELECT
                "taxonID" AS taxon_id,
                "scientificName" AS scientific_name,
                "scientificnameAuthorship" AS authorship,
                "taxonrank" AS taxon_rank,
                "taxonomicStatus" AS taxonomic_status
            FROM taxonomy
            WHERE {where_sql}
            ORDER BY "scientificName"
            LIMIT %s;
        """
        params.append(limit)

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
