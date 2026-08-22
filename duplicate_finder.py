import pandas as pd

excel_path = r"C:\path\to\folder\AcariUKDatabase\260822_AcReS_Data_Upload.xlsx"

pk_map = {
    'Samples': ['eventID'],
    'Observations': ['observationID'],
    'Observation_Demographics': ['demographicID'],
    'Specimens': ['specimenID'],
    'Taxonomy': ['taxonID'],
    'Literature': ['litID'],
    'Taxonomy_Literature_Junction': ['taxonid', 'litID', 'Type'],
    'Sample_Literature_Junction': ['eventID', 'litID', 'Type'],
    'Observation_Literature_Junction': ['observationID', 'litID', 'type']
}

print("--- AUDITING PRIMARY KEYS ---")
xls = pd.ExcelFile(excel_path)

for sheet_name, pk_cols in pk_map.items():
    df = pd.read_excel(xls, sheet_name=sheet_name)
    # Match column casing dynamically
    actual_cols = [c for c in df.columns for pk in pk_cols if c.lower() == pk.lower()]
    
    dups = df[df.duplicated(subset=actual_cols, keep=False)]
    if not dups.empty:
        print(f"\n❌ [{sheet_name}] Found {len(dups)} rows involved in duplicate PKs on {actual_cols}:")
        print(dups[actual_cols].drop_duplicates().to_string(index=False))
    else:
        print(f"✓ [{sheet_name}] All PKs unique.")
