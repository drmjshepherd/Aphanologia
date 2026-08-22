from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from typing import Optional
from database import get_db_connection
import json
import os

app = FastAPI(
    title="Aphanologia Acari Portal API",
    description="Spatial API endpoints serving British Acari records & PostGIS geometries",
    version="1.0.0"
)

# Serve the Interactive Web Map on Home Page
@app.get("/", response_class=FileResponse)
def serve_map():
    return FileResponse("index.html")

@app.get("/api/v1/observations/geojson")
def get_observations_geojson(
    limit: int = Query(500, description="Maximum number of spatial points to return", ge=1, le=5000),
    genus_or_species: Optional[str] = Query(None, description="Filter records by scientific name search (e.g. 'Veigaia')")
):
    """
    Queries PostGIS and converts sample/observation points into a GeoJSON FeatureCollection 
    suitable for Leaflet, MapLibre, or QGIS mapping web clients.
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

        if genus_or_species:
            sql += " AND t.\"scientificName\" ILIKE %s"
            params.append(f"%{genus_or_species}%")

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
