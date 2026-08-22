import pandas as pd
from sqlalchemy import create_engine, text
import sys

# ==========================================
# 1. CONFIGURATION & FILE PATH
# ==========================================
DB_USER = "postgres"
DB_PASS = "actual_password_here"  # <--- Update with your PostgreSQL password
DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "Aphanologia"

EXCEL_FILE_PATH = r"C:\path\to\folder\AcariUKDatabase\260822_AcReS_Data_Upload.xlsx"

# Mapping database tables to Excel sheet names
SHEETS_TO_TABLES = {
    "Samples": "samples",
    "Observations": "observations",
    "Observation_Demographics": "observation_demographics",
    "Specimens": "specimens",
    "Taxonomy": "taxonomy",
    "Literature": "literature",
    "Taxonomy_Literature_Junction": "taxonomy_literature_junction",
    "Sample_Literature_Junction": "sample_literature_junction",
    "Observation_Literature_Junction": "observation_literature_junction"
}

# ==========================================
# 2. DATABASE CONNECTION & POSTGIS ENUMS
# ==========================================
connection_string = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
engine = create_engine(connection_string)

print(f"Connecting to database '{DB_NAME}'...")

try:
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
        
        # Create Controlled Vocabularies (ENUMs) for sex and lifestage
        conn.execute(text("""
            DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'sex_enum') THEN
                    CREATE TYPE sex_enum AS ENUM ('male', 'female', 'mixed', 'undetermined');
                END IF;
                IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'lifestage_enum') THEN
                    CREATE TYPE lifestage_enum AS ENUM (
                        'egg', 'prolarva', 'larva', 'protonymph', 'deutonymph', 
                        'tritonymph', 'nymph', 'juvenile', 'adult', 'dead remains', 
                        'undetermined', 'sign', 'gall'
                    );
                END IF;
            END $$;
        """))
        conn.commit()
    print("✓ Connected successfully. PostGIS extension & ENUM types verified.")
except Exception as e:
    print(f"❌ Connection or setup failed: {e}")
    sys.exit(1)

# ==========================================
# 3. READ EXCEL & BULK INGESTION
# ==========================================
print(f"\nOpening workbook: {EXCEL_FILE_PATH}...")
excel = pd.ExcelFile(EXCEL_FILE_PATH)

for sheet_name, table_name in SHEETS_TO_TABLES.items():
    if sheet_name in excel.sheet_names:
        print(f"Reading tab '{sheet_name}'...")
        # Read as string to preserve pre-1900 dates, leading zeros, and Unicode characters
        df = pd.read_excel(excel, sheet_name=sheet_name, dtype=str)
        
        # Clean header and value whitespace across string columns
        df.columns = df.columns.str.strip()
        df = df.applymap(lambda x: x.strip() if isinstance(x, str) else x)
        
        # Load raw data into PostgreSQL
        df.to_sql(table_name, engine, if_exists="replace", index=False)
        print(f"  ✓ Uploaded {len(df)} rows into table '{table_name}'.")
    else:
        print(f"  ⚠️ Sheet '{sheet_name}' not found in workbook. Skipping.")

# ==========================================
# 4. PRIMARY KEYS, FOREIGN KEYS & GEOMETRIES
# ==========================================
print("\nStructuring relational constraints and spatial geometries...")

with engine.connect() as conn:
    # --- A. PostGIS Geometries on 'samples' ---
    print("  • Generating BNG (EPSG:27700) and WGS84 (EPSG:4326) PostGIS geometries...")
    conn.execute(text("""
        ALTER TABLE samples ADD COLUMN IF NOT EXISTS geom_bng geometry(Point, 27700);
        ALTER TABLE samples ADD COLUMN IF NOT EXISTS geom_wgs84 geometry(Point, 4326);
    """))
    
    conn.execute(text("""
        UPDATE samples 
        SET geom_bng = ST_SetSRID(ST_MakePoint(CAST(TRIM(bngx) AS float), CAST(TRIM(bngy) AS float)), 27700)
        WHERE bngx IS NOT NULL AND bngy IS NOT NULL 
          AND TRIM(bngx) != '' AND TRIM(bngy) != '';
        
        UPDATE samples 
        SET geom_wgs84 = ST_SetSRID(ST_MakePoint(CAST(TRIM("decimalLongitude") AS float), CAST(TRIM("decimalLatitude") AS float)), 4326)
        WHERE "decimalLongitude" IS NOT NULL AND "decimalLatitude" IS NOT NULL 
          AND TRIM("decimalLongitude") != '' AND TRIM("decimalLatitude") != '';
    """))

    # --- B. Primary Keys ---
    print("  • Applying Primary Keys...")
    conn.execute(text("""
        ALTER TABLE samples ADD PRIMARY KEY ("eventID");
        ALTER TABLE observations ADD PRIMARY KEY ("observationID");
        ALTER TABLE observation_demographics ADD PRIMARY KEY ("demographicID");
        ALTER TABLE specimens ADD PRIMARY KEY ("specimenID");
        ALTER TABLE taxonomy ADD PRIMARY KEY ("taxonID");
        ALTER TABLE literature ADD PRIMARY KEY ("litID");
        ALTER TABLE taxonomy_literature_junction ADD PRIMARY KEY ("taxonid", "litID", "Type");
        ALTER TABLE sample_literature_junction ADD PRIMARY KEY ("eventID", "litID", "Type");
        ALTER TABLE observation_literature_junction ADD PRIMARY KEY ("observationID", "litID", "type");
    """))

    # --- C. Foreign Keys ---
    print("  • Applying Foreign Keys...")
    conn.execute(text("""
        -- Observations links
        ALTER TABLE observations 
            ADD CONSTRAINT fk_obs_sample FOREIGN KEY ("eventID") REFERENCES samples("eventID"),
            ADD CONSTRAINT fk_obs_taxon FOREIGN KEY ("taxonID") REFERENCES taxonomy("taxonID");

        -- Demographics links
        ALTER TABLE observation_demographics 
            ADD CONSTRAINT fk_demo_obs FOREIGN KEY ("observationID") REFERENCES observations("observationID");

        -- Specimens links
        ALTER TABLE specimens 
            ADD CONSTRAINT fk_spec_demo FOREIGN KEY ("demographicID") REFERENCES observation_demographics("demographicID");

        -- Literature Junction links
        ALTER TABLE taxonomy_literature_junction 
            ADD CONSTRAINT fk_taxjunc_taxon FOREIGN KEY ("taxonid") REFERENCES taxonomy("taxonID"),
            ADD CONSTRAINT fk_taxjunc_lit FOREIGN KEY ("litID") REFERENCES literature("litID");

        ALTER TABLE sample_literature_junction 
            ADD CONSTRAINT fk_sampjunc_sample FOREIGN KEY ("eventID") REFERENCES samples("eventID"),
            ADD CONSTRAINT fk_sampjunc_lit FOREIGN KEY ("litID") REFERENCES literature("litID");

        ALTER TABLE observation_literature_junction 
            ADD CONSTRAINT fk_obsjunc_obs FOREIGN KEY ("observationID") REFERENCES observations("observationID"),
            ADD CONSTRAINT fk_obsjunc_lit FOREIGN KEY ("litID") REFERENCES literature("litID");
    """))

    conn.commit()

print("\n==========================================")
print("🎉 DATABASE STRUCTURE AND DATA UPLOAD COMPLETE!")
print("All 9 tables, PostGIS points, and Foreign Keys are live.")
print("==========================================")
