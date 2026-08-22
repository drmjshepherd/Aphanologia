from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from typing import Optional
from database import get_db_connection
import json

app = FastAPI(
    title="Aphanologia Acari Portal API",
    description="Spatial API endpoints serving British Acari records & PostGIS geometries",
    version="1.0.0"
)

@app.get("/", response_class=FileResponse)
def serve_map():
    return FileResponse("index.html")

@app.get("/api/v1/observations/geojson")
def get_observations_geojson(
    limit: int = Query(5000, description="Maximum number of spatial points to return", ge=1, le=50000),
    taxon_name: Optional[str] = Query(None, description="Filter records by scientific name"),
    start_year: Optional[int] = Query(None, description="Filter records from this year onward"),
    end_year: Optional[int] = Query(None, description="Filter records up to this year")
):
    """
    Queries PostGIS and converts sample/observation points into a GeoJSON FeatureCollection,
    filtered dynamically by taxon name and date range.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        sql = """
            SELECT 
                o."observationID",
                t."scientificName",
                t."taxonrank",
                s."eventID",
                s."earliestDateCollected",
                s."latestDateCollected",
                s."samplingLocation",
                s."gridRef",
                ST_AsGeoJSON(s.geom_wgs84)::json AS geometry
            FROM observations o
            JOIN taxonomy t ON o."taxonID" = t."taxonID"
            JOIN samples s ON o."eventID" = s."eventID"
            WHERE s.geom_wgs84 IS NOT NULL
        """
        params = []

        # Filter by Taxon Scientific Name (matches species, genus, family, suborder, etc.)
        if taxon_name and taxon_name.strip():
            sql += " AND t.\"scientificName\" ILIKE %s"
            params.append(f"%{taxon_name.strip()}%")

        # Filter by Start Year
        if start_year:
            sql += " AND EXTRACT(YEAR FROM s.\"earliestDateCollected\") >= %s"
            params.append(start_year)

        # Filter by End Year
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
