from fastapi import FastAPI, HTTPException, Query, Path
from fastapi.responses import FileResponse
from typing import Optional
from database import get_db_connection
import json
import re

app = FastAPI(
    title="Aphanologia Acari Portal API",
    description="Spatial API endpoints serving British Acari records & PostGIS geometries",
    version="1.1.0"
)

@app.get("/", response_class=FileResponse)
def serve_map():
    return FileResponse("index.html")

@app.get("/taxonomy", response_class=FileResponse)
def serve_taxonomy():
    return FileResponse("taxonomy.html")


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

    Two ways to filter by taxon:
      - taxon_id: the 'proper' way. Uses get_descendant_taxon_ids()
        (Query-1) to expand the chosen taxon out to every species
        and synonym beneath it, then returns observations of any
        of them. Also now resolves each observation through
        view_effective_observations, so manually-corrected
        misapplications and synonyms show up under their correct
        current name rather than the name originally written down.
      - taxon_name: kept for backwards compatibility with the
        existing map page; does a simple text search instead.
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
            sql += " AND EXTRACT(YEAR FROM s.\"earliestDateCollected\") >= %s"
            params.append(start_year)

        if end_year:
            sql += " AND EXTRACT(YEAR FROM s.\"earliestDateCollected\") <= %s"
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
                        "earliestDate": str(row["earliestDateCollected"]) if row["earliestDateCollected"] else None,
                        "latestDate": str(row["latestDateCollected"]) if row["latestDateCollected"] else None,
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
