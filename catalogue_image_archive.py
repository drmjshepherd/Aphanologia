"""
catalogue_image_archive.py

STAGE A - READ ONLY DIAGNOSTIC SCRIPT.
Makes NO changes to the database and NO changes to any files.

Walks the taxonomically-organised image archive folder and tries to
work out, for every folder and image found, which taxon and/or
observation it belongs to - based purely on the folder naming
convention. Writes CSV report files so you can review the matches
(and spot any mismatches or surprises) BEFORE any of this is used
to actually update the database.

DESIGN NOTE (v3): earlier versions decided "is this folder a
specimen folder?" by inspecting the folder's OWN children as a
whole. That broke whenever a species folder contained MORE THAN
ONE specimen subfolder (e.g. AcReS_2853 and AcReS_2854 side by
side) - the species folder got wrongly treated as a single
specimen itself, swallowing every image underneath without ever
recording the individual specimen folder names.

This version instead judges EACH CHILD FOLDER on its own name as
it's encountered: if a child's name matches a taxon-rank prefix
(or 'Undet_'), it's more taxonomy and we recurse into it. If not,
that child is treated as its own specimen candidate - however many
of them sit side by side under the same parent.
"""

import os
import re
import csv
from database import get_db_connection

# ---------------------------------------------------------------
# CONFIGURATION - adjust if needed
# ---------------------------------------------------------------
ARCHIVE_ROOT = r"C:\path\to\folder\Mesofauna Image Archive"
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.tif', '.tiff', '.bmp', '.gif'}

TAXON_FOLDER_REPORT = "archive_taxon_folders_report.csv"
SPECIMEN_FOLDER_REPORT = "archive_specimen_folders_report.csv"
EMPTY_FOLDER_REPORT = "archive_empty_folders_report.csv"

PREFIX_TO_RANK = {
    'C': 'class',
    'SbC': 'subclass',
    'SpO': 'superorder',
    'O': 'order',
    'SbO': 'suborder',
    'InO': 'infraorder',
    'HpO': 'hyporder',
    'PvO': 'parvorder',
    'SpF': 'superfamily',
    'F': 'family',
    'Family': 'family',
    'SbF': 'subfamily',
    'Subfamily': 'subfamily',
    'Genus': 'genus',
    'G': 'genus',
    'Species': 'species',
    'Sp': 'species',
}

ACRES_PATTERN = re.compile(r'AcReS[_\-]?(\d+)', re.IGNORECASE)


def load_taxonomy_lookup():
    """
    Loads every taxon name from the database once, into memory, as a
    dictionary mapping (lowercased scientific name) -> list of
    (taxonID, rank, taxonomicStatus).
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT "taxonID", "scientificName", "taxonrank", "taxonomicStatus"
        FROM taxonomy;
    """)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    lookup = {}
    for row in rows:
        key = row["scientificName"].strip().lower()
        lookup.setdefault(key, []).append(
            (row["taxonID"], row["taxonrank"], row["taxonomicStatus"])
        )
    return lookup


def parse_taxon_folder(folder_name):
    """
    Given a single folder name, works out whether it matches a known
    rank prefix (e.g. 'F_Rhagidiidae' -> ('family', 'Rhagidiidae')),
    an 'Undet_' folder, or neither.
    Returns (kind, rank_or_none, raw_name_text).
    """
    if '_' not in folder_name:
        return ('unrecognised', None, folder_name)

    prefix, rest = folder_name.split('_', 1)

    if prefix.lower() == 'undet':
        return ('undet', None, rest.replace('_', ' ').strip())

    rank = PREFIX_TO_RANK.get(prefix)
    if rank:
        return ('ranked', rank, rest.replace('_', ' ').strip())

    return ('unrecognised', None, folder_name)


def find_images(folder_path):
    """
    Recursively finds every image file under a given folder (a
    specimen folder might have its own subfolders, e.g. 'dorsal',
    'ventral', 'slide mount' etc.), WITHOUT opening or reading the
    files themselves - just listing their names and paths.
    """
    found = []
    for root, dirs, files in os.walk(folder_path):
        for f in files:
            if os.path.splitext(f)[1].lower() in IMAGE_EXTENSIONS:
                found.append(os.path.join(root, f))
    return found


def main():
    if not os.path.isdir(ARCHIVE_ROOT):
        print(f"ERROR: Could not find archive folder at:\n  {ARCHIVE_ROOT}")
        print("Check the path is correct and try again.")
        return

    print("Loading taxonomy table into memory for name matching...")
    taxonomy_lookup = load_taxonomy_lookup()
    print(f"  Loaded {len(taxonomy_lookup)} distinct names.\n")

    taxon_rows = []
    specimen_rows = []
    empty_folder_rows = []

    def handle_specimen_candidate(folder_path, breadcrumb):
        """
        Called for any folder whose NAME did not match a taxon-rank
        prefix. Treated as a specimen folder in its own right,
        regardless of what its siblings look like.
        """
        folder_name = os.path.basename(folder_path)
        images = find_images(folder_path)

        if len(images) == 0:
            empty_folder_rows.append({
                'folder_path': folder_path,
                'folder_name': folder_name,
                'taxon_breadcrumb': breadcrumb,
            })
            return

        acres_match = ACRES_PATTERN.search(folder_name)
        observation_id = acres_match.group(1) if acres_match else None

        specimen_rows.append({
            'folder_path': folder_path,
            'folder_name': folder_name,
            'taxon_breadcrumb': breadcrumb,
            'inferred_observationID': observation_id or '',
            'image_count': len(images),
            'example_image': images[0] if images else '',
        })

    def walk_taxon_folder(folder_path, breadcrumb):
        """
        Called for a folder we ALREADY know is a taxon-rank folder
        (or the archive root). Looks at each of its children
        individually: taxon-named children are recursed into as
        further taxonomy; anything else is handled as its own
        specimen candidate.
        """
        try:
            entries = sorted(os.listdir(folder_path))
        except (PermissionError, FileNotFoundError) as e:
            print(f"  WARNING: could not read folder, skipping: {folder_path} ({e})")
            return

        for entry in entries:
            full_path = os.path.join(folder_path, entry)
            if not os.path.isdir(full_path):
                continue  # ignore stray files sitting alongside folders

            kind, rank, raw_name = parse_taxon_folder(entry)

            if kind == 'ranked':
                candidate_name = raw_name
                matches = taxonomy_lookup.get(candidate_name.strip().lower(), [])

                taxon_rows.append({
                    'folder_path': full_path,
                    'folder_name': entry,
                    'inferred_rank': rank,
                    'candidate_name': candidate_name,
                    'match_count': len(matches),
                    'matched_taxonIDs': ', '.join(str(m[0]) for m in matches),
                    'matched_statuses': ', '.join(m[2] for m in matches),
                })
                walk_taxon_folder(full_path, f"{breadcrumb} > {candidate_name}")

            elif kind == 'undet':
                candidate_name = raw_name
                matches = taxonomy_lookup.get(candidate_name.strip().lower(), [])

                taxon_rows.append({
                    'folder_path': full_path,
                    'folder_name': entry,
                    'inferred_rank': 'UNDET',
                    'candidate_name': candidate_name,
                    'match_count': len(matches),
                    'matched_taxonIDs': ', '.join(str(m[0]) for m in matches),
                    'matched_statuses': ', '.join(m[2] for m in matches),
                })
                walk_taxon_folder(full_path, f"{breadcrumb} > Undet_{candidate_name}")

            else:
                # Doesn't match a taxon naming pattern - treat this
                # folder itself as a specimen candidate, whatever its
                # name (AcReS_2853, a plain number, anything else).
                handle_specimen_candidate(full_path, breadcrumb)

    print("Walking the archive folder - this may take a little while for a large archive...")
    walk_taxon_folder(ARCHIVE_ROOT, "")

    with open(TAXON_FOLDER_REPORT, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'folder_path', 'folder_name', 'inferred_rank',
            'candidate_name', 'match_count', 'matched_taxonIDs', 'matched_statuses'
        ])
        writer.writeheader()
        writer.writerows(taxon_rows)

    with open(SPECIMEN_FOLDER_REPORT, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'folder_path', 'folder_name', 'taxon_breadcrumb',
            'inferred_observationID', 'image_count', 'example_image'
        ])
        writer.writeheader()
        writer.writerows(specimen_rows)

    with open(EMPTY_FOLDER_REPORT, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['folder_path', 'folder_name', 'taxon_breadcrumb'])
        writer.writeheader()
        writer.writerows(empty_folder_rows)

    print(f"\nDone.")
    print(f"  Taxon folders examined:    {len(taxon_rows)}  -> {TAXON_FOLDER_REPORT}")
    print(f"  Specimen folders examined: {len(specimen_rows)}  -> {SPECIMEN_FOLDER_REPORT}")
    print(f"  Empty placeholder folders: {len(empty_folder_rows)}  -> {EMPTY_FOLDER_REPORT}")

    no_match = [r for r in taxon_rows if r['match_count'] == 0]
    multi_match = [r for r in taxon_rows if r['match_count'] > 1]
    with_acres = [r for r in specimen_rows if r['inferred_observationID']]

    print(f"\n  Taxon folders with NO database match: {len(no_match)}")
    print(f"  Taxon folders with MULTIPLE database matches: {len(multi_match)}")
    print(f"  Specimen folders WITH an AcReS number found: {len(with_acres)}")
    print(f"  Specimen folders WITHOUT an AcReS number: {len(specimen_rows) - len(with_acres)}")


if __name__ == "__main__":
    main()
