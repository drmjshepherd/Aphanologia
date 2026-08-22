import os
import pandas as pd
import psycopg2

# Database Connection Settings
DB_CONFIG = {
    "dbname": "Aphanologia",
    "user": "postgres",
    "password": "your_password_here",  # Replace with your PostgreSQL password
    "host": "localhost",
    "port": 5432
}

# Excel file path
EXCEL_FILE = r"C:\path\to\folder\AcariUKDatabase\260822_AcReS_Data_Upload.xlsx"
SHEET_NAME = "manual_taxonomy_update"

def import_manual_taxonomy_updates():
    if not os.path.exists(EXCEL_FILE):
        print(f"Error: File not found at {EXCEL_FILE}")
        return

    print(f"Reading '{SHEET_NAME}' from {EXCEL_FILE}...")
    try:
        df = pd.read_excel(EXCEL_FILE, sheet_name=SHEET_NAME)
    except Exception as e:
        print(f"Error reading Excel sheet: {e}")
        return
    
    # Clean whitespace from column headers
    df.columns = [str(col).strip() for col in df.columns]
    print(f"Columns found in sheet: {list(df.columns)}")
    print(f"Total rows to process: {len(df)}")

    # Connect to PostgreSQL
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
    except Exception as e:
        print(f"Database connection error: {e}")
        return

    try:
        # 1. Create dedicated override table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS observation_taxonomy_override (
                observation_id TEXT PRIMARY KEY REFERENCES observations("observationID") ON DELETE CASCADE,
                revised_taxon_id TEXT NOT NULL REFERENCES taxonomy("taxonID"),
                reason_or_notes TEXT,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 2. Insert/Update records using ON CONFLICT to make script re-runnable
        insert_sql = """
            INSERT INTO observation_taxonomy_override (observation_id, revised_taxon_id, reason_or_notes)
            VALUES (%s, %s, %s)
            ON CONFLICT (observation_id) 
            DO UPDATE SET 
                revised_taxon_id = EXCLUDED.revised_taxon_id,
                reason_or_notes = EXCLUDED.reason_or_notes,
                updated_at = CURRENT_TIMESTAMP;
        """

        records = []
        for idx, row in df.iterrows():
            obs_id = str(row.get("observationID", "")).strip()
            
            # Match 'revisedtaxonID' exactly as printed in your output
            revised_id = None
            for col in ["revisedtaxonID", "revised_taxonID", "revisedTaxonID", "taxonID", "revised_taxon_id"]:
                if col in row and pd.notna(row[col]):
                    revised_id = str(row[col]).strip()
                    break

            notes = None
            for col in ["notes", "reason", "comment"]:
                if col in row and pd.notna(row[col]):
                    notes = str(row[col]).strip()
                    break

            if obs_id and revised_id:
                records.append((obs_id, revised_id, notes))

        print(f"Prepared {len(records)} valid rows for database insertion.")
        
        cursor.executemany(insert_sql, records)
        conn.commit()
        print(f"Successfully imported {len(records)} manual taxonomy overrides into PostgreSQL table 'observation_taxonomy_override'.")

    except Exception as e:
        conn.rollback()
        print(f"SQL Execution Error: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    import_manual_taxonomy_updates()
