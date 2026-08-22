# Aphanologia
A web-based PostgreSQL database for exploring and displaying infomration about soil organisms and other obscure groups in the UK.

## Creating a database for exploring soil organism observations in the UK

### Background
I have recently completed an audit of 24990 records of acari observed in Great Britain, and every entry has now been matched to a valid scientific name according a synonymic taxonomic database i've constructed to support the assignment of records from British mite research, and help generate a national species list. Of the 2479 species of acari thought to be in the UK, i have amassed records of at least one observation of 1653 of these. The remaining species have been listed in more general documents (e.g. international reviews of a taxon group which notes “Great Britain” as a known location, or attempts at past species lists where the sources of the observations aren’t clear.  There are probably also some, like Hermannia scabra, which have been recorded under this name, but all of whose records have been proven to be likely to refer to Hermannia nodosa – I may remove these from the list in due course.  All this data, and other data mentioned below, are currently in an Excel spreadsheet.

This project aims to use these 2 datasets to form the basis of an online database which will allow people to view and map British observations of acari, at a range of taxonomic levels, download data, view information about species found together in the same sample, view or download photographs of identified specimens, view taxonomic information about the species (other names applied to this species in the UK), get references, or even link to downloadable documents, relating to the species, its observations identification and taxonomy.  The database should also allow superusers to update taxonomic relationships, add additional records, or add other information to the database.  The database should be compatible with, and ideally linked to, the NBN atlas, the UK species inventory and the GBIF.

Various tables were created (needs combining with the final table schema below!)

The taxonomy part of the database includes the following information
* taxonid	A unique number relating to the taxon name
* parentNameUsageID	The unique number of the parent (either a higher parent taxon or the correct name for synonyms or misapplications)
* scientificName	The binomial or trionomial name.  Subspecies are written as a 3 word trinomial, varieties have the variety name preceded by “var. ” and formas have the forma name preceded by “f. ”
* taxonrank	The rank of the taxon including kingdom, phylum, class, superorder, order, suborder, infraorder, hyporder, parvorder, microrder, nanorder, superfamily, family, subfamily, genus, species, subspecies, *
variety, forma.  Note that I have chosen to include names that include subgenera as a “synonym” but included “valid name with subgenus”, to keep the logic clean.
* scientificnameAuthorship	The name and date of the author that first described the species with names in brackets for instances where the root name is retained or merely adapted, “sensu Name, date” for * misapplications or “non Author, date” for instances where multiple authors have erected the same name independently.
* taxonomicStatus	Is either “accepted”, “doubtful”, “misapplied” or “synonym”
* nomenclaturalStatus	may be: invalid - superseded basionym; invalid - junior synonym; invalid - subsequent combination of basionym; invalid - literature misspelling; misapplied; species inquirenda; invalid - subsequent combination of junior synonym; invalid - misspelled or invalid basionym; invalid - misspelled or invalid junior synonym; valid name with subgenus; nomen dubium 
* taxonRemarks	Notes on synonymy and justification for presence in UK species list, where known


I also have a Observations sheet for individual (or grouped) observations, mostly harvested from the literature.  This includes:
* Unique identifier	A unique reference number preceded by AcReS (Acari Recordign Scheme)
date collected min	the earliest date possible for the observation
corrected date collected max	the latest date possible for the observation 
* Collected/Photo By	The name of the person that observed the animal or took a photograph, to allow ID by another person.
* ID by	The person identifying the animal
* GUID	The unique taxon name originally recorded, or, if taxonomy manually updated, one that matches the entry (e.g. Macrochelid sp. Original entry might match to the GUID for Macrochelidae, Anoetidae would match to the GUID for Histiostomatidae, Eriophyid sp recorded in 1921 would match to Eriophyoidea because it could now refer to several families etc.

I have a samples sheet describing the characteristics of the sample where the organisms were collected or site characteristics where they were observed.
* sampleID	A unique number assigned to each individual sampling event (could be a single observation of a single specimen, a group of specimens observed together, a community extracted by a tullgren extract, or a collection of Tullgren funnel extracts bulked from a single site over a period of a year, if all bulked and reported together.  Characterised by:
* SHADe code	This is a microhabitat recording system based on a code where Substrates(S) are described by 4 letters (TsSc woud refer to Timber – soft rot Soil clayey, and would refer to a soft rotting piece of wood lying on clayey soil with the organism found at the interface. Humidity regime (H) (a number from 1 to 7 where 7 is continuously submerged, and 1 is continuously dry e.g. stored products), Acidity/Alkalinity (A)– an estimate of the pH to the nearest whole number of the situation where appropriate (normally just for soils compost manures, dung etc.), and DisturbancE (De) – how long this situation has existed (from 7: centuries (including regular cyclic change e.g. tides, forest leaf fall) to 1: more or less constantly disturbed.  Missing or unknown data is represented by “X” or “x” and the elements are separated by hyphens for easy reading (e.g. TsSc-5-6-5 – Soft rotting wood lying on clayey soil that almost never dries out – only after a fully dry month  on pH 6 soil, that has been in place for between a decade and a century). This column also contains other text microhabitats which don’t follow this format.
* Habitat	UK Broad habitat type
* Specimen location	where the specimen is store, if available.
* Notes	general notes on the observation – more details on habitat, microhabitat, type of sample taken, associations with other specific animals/plants, or notes on taxonomic assignment of this obseration.
* Postcode	Location as postcode
* Lat (WGS84)	latitude
* long (WGS84)	longitude
* gridref	OS landranger type grid reference
* BNG X	British nation grid eastings
* BNG Y	British national grid northings
* location (text)	Place name
* Accuracy (radius in metres)	estimated area around central recorded point, to where record could refer
* entered on	Date entered into database 
* entered by	Person entering data
* Public or restricted	nature of data record (some are restricted)
* Data licence holder	if restricted, who holds the licence
* Data source	The full publication reference (good to make this link to literature table with a number, or type of collection (monitoring programme, personal collection, photo posted on facebook group etc.)

I have also created a literature table comprising the following headings:
* litID	a unique number for each pubnlication
* title	title of publication
* author	the author(s) of  the publication, in format Surname, A.B.C – additional authors separated by further commas and final author separated by “&”
* year	Year of publication
* publication	The journal or book in which the article was published
* sourceURL	Where the article may be viewed or downloaded online
* litnotes	notes on this publication.

I’ve produced a junction table linking sampleID with litID, so every sample is referenced.
I’d like to use the lit table also to reference “as used in”, “first published in”, “synonymy from” and “ID literature” in the taxonomy table.
There are still some issues with the data set (inconsistent use of SHADEs, some literature names spelt out in full) but I’m keen to see if we can build the database and tidy up the issues more easily from within a database format, as using Excel is getting pretty difficult.
Given the ambitions above, and the data I have outlined to start off with, please can you outline the steps I’d need to take to get me from this current situation to the online database ambition I’ve outlined?  I’m no expert in this (my expertise is in soil biology, not database building!) so I’ll need to be walked through each step.  I feel I’ve carried out the largest data hygiene task, but if there are others I should complete before leaving excel then please let me know.
In the past you’ve suggested a PostGRES (SQL?) geodatabase, perhaps with a Django GUI (front end).  However, I’m happy to proceed with whatever you think is best.

### Aim and requirements

i) maintain a secure, flexibly query-able record of acari observations in the UK, linked to typical recorder informmation, groupable by samples, linked to relevant literature used to identify, source an observation, or provide taxonomic details, and linked to other data such as photographs, barcodes, etc.

ii) make this database available online in a secure manner, so that ordinary users can view standard query outputs and submit data records for review and (if approved) subsequent inclusion, while super-users can add data to all tables, and maybe hyper users can revise the database schema and architecture.

iii) allow upload of records (either for review or pre-reviewed by superusers), either on the basis of individual observations (which would also generate individual sample eventIDs) or as dataset uploads.
      a) The individual record upload should allow for some flexibility in entry (e.g. they can fill in the eventID details, then add species to the eventID one at a time (e.g. with an "add another observation from this sample" button). It would be good to allow editing before they submit, and also allow them to withdraw and edit any records that haven't yet been verified.
     b) The dataset upload should allow users to select the columns that they can enter from their data, and allow them to generate a template for upload that will already have the correct columns, complete with a metadata page explaining what should go in each column).  I'm guessing that this will smooth the process and encourage people to record useful parameters.

iv) allow casual users to browse taxonomy of British acari, using a dynamic menu that allows them to "drill down" from higher to lower taxa, opening up groups of child taxa offset, and with linking lines, under parent taxa, from Kingdom, all the way down to "forma", and covering all the taxonomic ranks used in acarology, including sub, infra, hyp, parv, micr, and nan-orders.  Under the valid species, these should include a further list of known synonyms.  Each taxon can be clicked on to view taxonomic inofmraiton and notes...  All taxa should be searchable using boolean searches, which will link to any taxonomic entry, accepted or not.

v) When a taxon is selected, the screen will display maps showing the distribution across the UK (the mites of Northern Ireland, however, have traditionally been recorded as part of Ireland, by Tom Bolger and others at UCD).  This should include the channel islands, and Isle of Man, but not other overseas crown protectorates (e.g. falklands etc.)..  The maps should also have some summary data, and controls in their legend, allowing users to set date ranges, or view accuracy radii showing the precision of the record.  Clicking on individual records on the map should bring up their observation data.

vi) the taxonomy pages should scrape photographs from specimen data to display, ideally showing the most "popular" image of the taxon first, then allowing "more photos" to be clicked on to show a full gallery.
Source data

Taxonomic lists initially from Turk, 1953, NHML mite species lists, Gledhill and Viets, Luxton oribatid lists
Records harvested from many sources, including extensive review of past literature and capture from historic published sources.
Some data from recent Natural England research, CEH research etc.
Also personal observations, photos from Facebook group etc.
Data arranged into this final schema of tables ready for a final python script to upload.  I'll give the name of the excel tab where the table is found, then a colon, and then all the headers - let me know if you need to know anything specific about the data under these headers if it's not clear.

Samples: eventID	samplingLocation	decimalLatitude	decimalLongitude	coordinateuncertaintyinmeters	bngx	bngy	gridRef	earliestDateCollected	latestDateCollected	habitat	SHADe	microhabitat	samplingProtocol	samplesizeValue	samplesizeUnit	recordedBy	eventRemarks	datarestricted	licenceHolder	dataSource

Observations: observationID	eventID	taxonID	identifiedBy	identificationVerificationStatus	verifiedBy	identificationRemarks	collectionID	catalogNumber	basisOfRecord	idTechnique	idReference[LitID]	idText[free_text]	occurrenceRemarks

Observation_Demographics: demographicID	observationID	sex	lifestage	count	density	densityUnit	minCount	maxCount	countDescription

Specimens: specimenID	demographicID	specCount	specBarcode	specPhotos	specLocation	specRef	specPreservation	specType	specComments

Taxonomy: taxonID	parentNameUsageID	scientificName	taxonrank	scientificnameAuthorship	taxonomicStatus	nomenclaturalStatus	acceptednameusageid	taxonRemarks

Literature: litID	articleTitle	authorName	editorName	yearPublished	publicationTitle	publicationSeries	publicationVolume	publicationIssue	publicationTotalpages	publicationPages	publishedBy	publicationISBNorISSN	publicationDOI	sourceURL	litNotes

Taxonomy_Literature_Junction: taxonid	Type	litID

Sample_Literature_Junction: eventID	Type	litID

Observation_Literature_Junction: observationID	type	litID

All these tables are represented in a single excel spreadsheet saved to:

C:\path\to\folder\AcariUKDatabase\260822_AcReS_Data_Upload.xlsx

# Database setup
I created the database Aphanologia (meaning knowledge of hidden things) using pgAdmin 4 and postGreSQL
(check older AI chats for details)
## Importing data
### Ensure Prerequisites
Open Command Prompt (Win + R, type cmd, hit Enter) and ensure the necessary Python bridge packages are installed:
```
pip install pandas openpyxl sqlalchemy psycopg2 geoalchemy2
```


### Duplicate Primary Key Finder Script
The following script checks for duplicates in the primary key

[duplicate_finder.py](duplicate_finder.py)

### Upload data to databse
Checked records were into the database Aphanologia using this import script

[upload_acres_db.py](upload_acres_db.py)

This produced the following output:
```
Connecting to database 'Aphanologia'...

✓ Connected successfully. PostGIS extension & ENUM types verified.



Opening workbook: C:\path\to\folder\AcariUKDatabase\260822_AcReS_Data_Upload.xlsx...

Reading tab 'Samples'...

C:\path\to\folder\AcariUKDatabase\upload_acres_db.py:76: FutureWarning: DataFrame.applymap has been deprecated. Use DataFrame.map instead.

  df = df.applymap(lambda x: x.strip() if isinstance(x, str) else x)

  ✓ Uploaded 10093 rows into table 'samples'.

Reading tab 'Observations'...

C:\path\to\folder\AcariUKDatabase\upload_acres_db.py:76: FutureWarning: DataFrame.applymap has been deprecated. Use DataFrame.map instead.

  df = df.applymap(lambda x: x.strip() if isinstance(x, str) else x)

  ✓ Uploaded 24991 rows into table 'observations'.

Reading tab 'Observation_Demographics'...

C:\path\to\folder\AcariUKDatabase\upload_acres_db.py:76: FutureWarning: DataFrame.applymap has been deprecated. Use DataFrame.map instead.

  df = df.applymap(lambda x: x.strip() if isinstance(x, str) else x)

  ✓ Uploaded 4919 rows into table 'observation_demographics'.

Reading tab 'Specimens'...

C:\path\to\folder\AcariUKDatabase\upload_acres_db.py:76: FutureWarning: DataFrame.applymap has been deprecated. Use DataFrame.map instead.

  df = df.applymap(lambda x: x.strip() if isinstance(x, str) else x)

  ✓ Uploaded 129 rows into table 'specimens'.

Reading tab 'Taxonomy'...

C:\path\to\folder\AcariUKDatabase\upload_acres_db.py:76: FutureWarning: DataFrame.applymap has been deprecated. Use DataFrame.map instead.

  df = df.applymap(lambda x: x.strip() if isinstance(x, str) else x)

  ✓ Uploaded 8304 rows into table 'taxonomy'.

Reading tab 'Literature'...

C:\path\to\folder\AcariUKDatabase\upload_acres_db.py:76: FutureWarning: DataFrame.applymap has been deprecated. Use DataFrame.map instead.

  df = df.applymap(lambda x: x.strip() if isinstance(x, str) else x)

  ✓ Uploaded 375 rows into table 'literature'.

Reading tab 'Taxonomy_Literature_Junction'...

C:\path\to\folder\AcariUKDatabase\upload_acres_db.py:76: FutureWarning: DataFrame.applymap has been deprecated. Use DataFrame.map instead.

  df = df.applymap(lambda x: x.strip() if isinstance(x, str) else x)

  ✓ Uploaded 733 rows into table 'taxonomy_literature_junction'.

Reading tab 'Sample_Literature_Junction'...

C:\path\to\folder\AcariUKDatabase\upload_acres_db.py:76: FutureWarning: DataFrame.applymap has been deprecated. Use DataFrame.map instead.

  df = df.applymap(lambda x: x.strip() if isinstance(x, str) else x)

  ✓ Uploaded 5425 rows into table 'sample_literature_junction'.

Reading tab 'Observation_Literature_Junction'...

C:\path\to\folder\AcariUKDatabase\upload_acres_db.py:76: FutureWarning: DataFrame.applymap has been deprecated. Use DataFrame.map instead.

  df = df.applymap(lambda x: x.strip() if isinstance(x, str) else x)

  ✓ Uploaded 73 rows into table 'observation_literature_junction'.


Structuring relational constraints and spatial geometries...

  • Generating BNG (EPSG:27700) and WGS84 (EPSG:4326) PostGIS geometries...

  • Applying Primary Keys...

  • Applying Foreign Keys...



==========================================

🎉 DATABASE STRUCTURE AND DATA UPLOAD COMPLETE!

All 9 tables, PostGIS points, and Foreign Keys are live.

==========================================
```

This verification script was run as an SQL query in pgAdmin 4

[verify_database_structure.sql](verify_database_structure.sql)

This produced the output:
"table_name"	"total_rows"	"bng_geoms_built"	"wgs_geoms_built"
"literature"	375		
"observation_demographics"	4919		
"taxonomy"	8304		
"observations"	24991		
"samples"	10093	10090	8423

This script was run as a query in pgAdmin 4 to ensure fast spatial queries when connecting to QGIS, bounding box filters, or running spatial joins. It builds GiST spatial indexes and B-tree indexes on the foreign keys:
-- 1. Build GiST Spatial Indexes for PostGIS
CREATE INDEX IF NOT EXISTS idx_samples_geom_bng ON samples USING gist (geom_bng);
CREATE INDEX IF NOT EXISTS idx_samples_geom_wgs84 ON samples USING gist (geom_wgs84);

-- 2. Build B-tree Indexes on Foreign Keys for fast JOIN performance
CREATE INDEX IF NOT EXISTS idx_obs_eventid ON observations ("eventID");
CREATE INDEX IF NOT EXISTS idx_obs_taxonid ON observations ("taxonID");
CREATE INDEX IF NOT EXISTS idx_demo_obsid ON observation_demographics ("observationID");
CREATE INDEX IF NOT EXISTS idx_spec_demoid ON specimens ("demographicID");
Once in SQL, the database schema was refined to ensure future compatibility with standard biological database structures and allow flexibility.
To ensure you don't have to re-architect later, here are key standard mechanisms used by major biological record centers (NBN, GBIF, iRecord) built right into the schema extension below:

1.	Identification Key Linkages: Extending taxonomy_literature_junction with matrix flags (is_key, key_coverage_rank, url_link) so users can click a genus/family and immediately get a link to the online key or paper needed to reach species.

2.	Darwin Core / GBIF / NBN Atlas Syncing: Adding fields for gbif_dataset_id, dwc_occurrence_id (UUID), sensitivity_precision (for obfuscating rare species locations if needed), and sync timestamps (last_gbif_sync).

3.	Audit Trail & Verification: A standard NBN status workflow (pending, verified, queried, rejected) attached to every observation, tracking who verified it and when.

4.	Media & Molecular Barcodes: Dedicated tables for photographs (with thumbnail URLs, primary image flags, license/copyright metadata) and DNA barcode sequences (COI, 18S, ITS).

This script was run to effect these changes:
-- =========================================================================
-- 1. EXTEND LITERATURE JUNCTION FOR IDENTIFICATION KEYS & ONLINE RESOURCES
-- =========================================================================
ALTER TABLE taxonomy_literature_junction 
  ADD COLUMN IF NOT EXISTS is_identification_key BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS key_scope_rank VARCHAR(50),
  ADD COLUMN IF NOT EXISTS online_resource_url TEXT,
  ADD COLUMN IF NOT EXISTS access_notes TEXT;

-- =========================================================================
-- 2. ADD VERIFICATION STATUS & GBIF / NBN ATLAS SYNC FIELDS TO OBSERVATIONS
-- =========================================================================
ALTER TABLE observations 
  ADD COLUMN IF NOT EXISTS verification_status VARCHAR(30) DEFAULT 'unverified',
  ADD COLUMN IF NOT EXISTS verified_by VARCHAR(150),
  ADD COLUMN IF NOT EXISTS verified_date TIMESTAMP WITH TIME ZONE,
  ADD COLUMN IF NOT EXISTS verification_notes TEXT,
  ADD COLUMN IF NOT EXISTS dwc_occurrence_id UUID DEFAULT gen_random_uuid(),
  ADD COLUMN IF NOT EXISTS share_with_nbn BOOLEAN DEFAULT TRUE,
  ADD COLUMN IF NOT EXISTS share_with_gbif BOOLEAN DEFAULT TRUE,
  ADD COLUMN IF NOT EXISTS nbn_export_date TIMESTAMP WITH TIME ZONE,
  ADD COLUMN IF NOT EXISTS coordinate_uncertainty_meters INT DEFAULT 100;

-- =========================================================================
-- 3. SPECIMEN MEDIA / PHOTOGRAPHS TABLE (TYPE MATCHED)
-- =========================================================================
CREATE TABLE IF NOT EXISTS observation_media (
    media_id SERIAL PRIMARY KEY,
    observation_id TEXT REFERENCES observations("observationID") ON DELETE CASCADE,
    specimen_id TEXT REFERENCES specimens("specimenID") ON DELETE SET NULL,
    media_type VARCHAR(50) DEFAULT 'photo',
    file_url TEXT NOT NULL,
    thumbnail_url TEXT,
    caption TEXT,
    photographer VARCHAR(150),
    license VARCHAR(50) DEFAULT 'CC-BY-4.0',
    is_primary_for_taxon BOOLEAN DEFAULT FALSE,
    community_votes INT DEFAULT 0,
    uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- =========================================================================
-- 4. MOLECULAR / DNA BARCODE TABLE (TYPE MATCHED)
-- =========================================================================
CREATE TABLE IF NOT EXISTS specimen_barcodes (
    barcode_id SERIAL PRIMARY KEY,
    specimen_id TEXT REFERENCES specimens("specimenID") ON DELETE CASCADE,
    gene_target VARCHAR(50) NOT NULL,
    ncbi_genbank_accession VARCHAR(50),
    bold_process_id VARCHAR(50),
    sequence_data TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- =========================================================================
-- 5. INDEXES FOR FAST API / SPATIAL LOOKUPS
-- =========================================================================
CREATE INDEX IF NOT EXISTS idx_obs_verification ON observations(verification_status);
CREATE INDEX IF NOT EXISTS idx_media_obs ON observation_media(observation_id);
CREATE INDEX IF NOT EXISTS idx_tax_lit_key ON taxonomy_literature_junction(is_identification_key);
Set up FastAPI for web interface
Think of Python as the engine that sits between your PostGIS database and the web browser. FastAPI is a popular Python framework used to build web applications and APIs (Application Programming Interfaces). The API acts as a translator: when a browser asks, "Show me all Acari records in Devon," FastAPI queries your local PostgreSQL database, converts the spatial points into a standard web format (GeoJSON), and sends it to the web page to display on a map.
Create a new folder called
Aphanologia_Web
And inside this folder create a virtual python environment in bash
python -m venv venv
Activate this environment in powershell
cd "C:\path\to\folder\AcariUKDatabase\Aphanologia_Web"
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
.\venv\Scripts\Activate.ps1
pip install fastapi uvicorn asyncpg psycopg2-binary pydantic
now create and edit main.py in the folder Aphanologia_Web
#main.py
from fastapi import FastAPI, HTTPException, Query
from typing import Optional
from database import get_db_connection
import json

app = FastAPI(
    title="Aphanologia Acari Portal API",
    description="Spatial API endpoints serving British Acari records & PostGIS geometries",
    version="1.0.0"
)

@app.get("/")
def home():
    return {
        "system": "Aphanologia Biological Recording Portal",
        "status": "Online (Local Development Environment)",
        "scope": "Acari of the United Kingdom",
        "database": "PostgreSQL / PostGIS (Aphanologia)"
    }

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
        # SQL aligned to exact table schema
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
        conn.close()Start the local server with Uvicorn
uvicorn main:app --reload
Then test it by pasting this into the address bar of a browser:
http://127.0.0.1:8000
and
http://127.0.0.1:8000/docs
To connect FastAPI to PostgreSQL and create that spatial GeoJSON endpoint.
Step 1: Create a Database Connection Module (database.py)
In the same Aphanologia_Web folder, create a new file named database.py.
Paste the following code into database.py (adjust the password on line 6 if your local PostgreSQL superuser password is set to something other than postgres):
import psycopg2
from psycopg2.extras import RealDictCursor

# Database Connection Parameters
DB_CONFIG = {
    "dbname": "Aphanologia",
    "user": "postgres",
    "password": "actual_password_here",  # <--- UPDATE THIS to your local PostgreSQL password
    "host": "localhost",
    "port": "5432"
}

def get_db_connection():
    """Establishes and returns a connection to the local Aphanologia PostGIS database."""
    try:
        conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
        return conn
    except Exception as e:
        print(f"❌ Error connecting to Aphanologia database: {e}")
        raise e
Create a html file in Aphalolgia_Web called index.html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Aphanologia - UK Acari Distribution Map</title>
    
    <!-- Leaflet CSS for Map Styling -->
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    
    <style>
        body { margin: 0; padding: 0; font-family: Arial, sans-serif; }
        #header { height: 50px; background: #1b4332; color: white; display: flex; align-items: center; padding: 0 20px; }
        #header h1 { margin: 0; font-size: 1.2rem; }
        #map { height: calc(100vh - 50px); width: 100%; }
        .leaflet-popup-content { font-size: 13px; line-height: 1.5; }
        .popup-title { font-weight: bold; font-style: italic; color: #1b4332; font-size: 14px; }
    </style>
</head>
<body>

    <div id="header">
        <h1>Aphanologia: British Acari Biological Records Map</h1>
    </div>
    
    <div id="map"></div>

    <!-- Leaflet JavaScript Library -->
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    
    <script>
        // Initialize Map centered on the United Kingdom
        const map = L.map('map').setView([54.5, -4.0], 6);

        // Add OpenStreetMap Tile Layer
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; OpenStreetMap contributors | Aphanologia Portal'
        }).addTo(map);

        // Fetch Live GeoJSON from your FastAPI Endpoint (Limit 500 records)
        fetch('/api/v1/observations/geojson?limit=500')
            .then(response => response.json())
            .then(data => {
                // Add GeoJSON Points to the Map
                L.geoJSON(data, {
                    pointToLayer: function (feature, latlng) {
                        return L.circleMarker(latlng, {
                            radius: 6,
                            fillColor: "#2d6a4f",
                            color: "#081c15",
                            weight: 1,
                            opacity: 1,
                            fillOpacity: 0.8
                        });
                    },
                    onEachFeature: function (feature, layer) {
                        const props = feature.properties;
                        const popupContent = `
                            <div class="popup-title">${props.scientificName}</div>
                            <b>Rank:</b> ${props.taxonRank}<br>
                            <b>Grid Ref:</b> ${props.gridRef || 'N/A'}<br>
                            <b>Date:</b> ${props.earliestDate || 'N/A'}<br>
                            <b>Location:</b> ${props.samplingLocation || 'Unspecified'}<br>
                            <small>Observation ID: ${props.observationID}</small>
                        `;
                        layer.bindPopup(popupContent);
                    }
                }).addTo(map);
            })
            .catch(error => console.error('Error loading GeoJSON:', error));
    </script>
</body>
</html>

