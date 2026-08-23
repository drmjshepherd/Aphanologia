"""
import_media_archive.py

STAGE B - WRITES TO THE DATABASE.

Walks the taxonomically-organised image archive and inserts one row
into observation_media per image found, linking each photo either to
a specific observation (where an AcReS_[number] folder was found and
matches a real observationID) or to a taxon generally (Tier 2 - the
majority of the archive, per the design agreed after reviewing the
Stage A diagnostic reports).

SAFE TO RE-RUN: before inserting, the script loads every file path
already recorded in observation_media and skips anything already
present, so running this again later (e.g. after adding more photos,
fixing a misspelled folder, or adding a missing taxon) will only add
what's new.

USAGE:
    python import_media_archive.py --dry-run     (show what WOULD happen, changes nothing)
    python import_media_archive.py                (actually writes to the database)

Always run with --dry-run first after making any change to this
script or to the archive folder structure.
"""

import os
import re
import csv
import sys
import argparse
from database import get_db_connection

ARCHIVE_ROOT = r"C:\path\to\folder\Mesofauna Image Archive"
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.tif', '.tiff', '.bmp', '.gif'}

PREFIX_TO_RANK = {
    'C': 'class', 'SbC': 'subclass', 'SpO': 'superorder', 'O': 'order',
    'SbO': 'suborder', 'InO': 'infraorder', 'HpO': 'hyporder', 'PvO': 'parvorder',
    'SpF': 'superfamily', 'F': 'family', 'Family': 'family',
    'SbF': 'subfamily', 'Subfamily': 'subfamily',
    'Genus': 'genus', 'G': 'genus', 'Species': 'species', 'Sp': 'species',
}

ACRES_PATTERN = re.compile(r'AcReS[_\-]?(\d+)', re.IGNORECASE)

NEEDS_ATTENTION_REPORT = "import_needs_attention.csv"
AMBIGUOUS_DEFAULT_REPORT = "import_ambiguous_defaults_applied.csv"
INSERTED_REPORT = "import_inserted_summary.csv"


def load_taxonomy_lookup(cursor):
    cursor.execute("""
        SELECT "taxonID", "scientificName", "taxonrank", "taxonomicStatus"
        FROM taxonomy;
    """)
    lookup = {}
    for row in cursor.fetchall():
        key = row["scientificName"].strip().lower()
        lookup.setdefault(key, []).append(
            (row["taxonID"], row["taxonrank"], row["taxonomicStatus"])
        )
    return lookup


def resolve_taxon_folder_name(name, lookup, ambiguous_log):
    """
    Given a candidate name from a folder, returns a single taxonID
    to use, or None if it can't be confidently resolved.

    - No matches at all: returns None (genuine gap - needs a folder
      fix or a new taxonomy entry).
    - Exactly one match: use it directly.
    - Multiple matches: use the single 'accepted' entry if there is
      EXACTLY one accepted match among them (per the agreed default
      for the archive's modern photos), and log that a default was
      applied. If there isn't exactly one accepted match, treat as
      unresolved rather than guessing further.
    """
    matches = lookup.get(name.strip().lower(), [])
    if len(matches) == 0:
        return None
    if len(matches) == 1:
        return matches[0][0]

    accepted_matches = [m for m in matches if m[2] == 'accepted']
    if len(accepted_matches) == 1:
        ambiguous_log.append({
            'candidate_name': name,
            'chosen_taxonID': accepted_matches[0][0],
            'all_matching_taxonIDs': ', '.join(str(m[0]) for m in matches),
        })
        return accepted_matches[0][0]

    return None  # genuinely ambiguous even after the default rule - skip


def parse_taxon_folder(folder_name):
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
    found = []
    for root, dirs, files in os.walk(folder_path):
        for f in files:
            if os.path.splitext(f)[1].lower() in IMAGE_EXTENSIONS:
                found.append(os.path.join(root, f))
    return found


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true',
                         help="Show what would happen without changing the database")
    args = parser.parse_args()

    if not os.path.isdir(ARCHIVE_ROOT):
        print(f"ERROR: Could not find archive folder at:\n  {ARCHIVE_ROOT}")
        return

    conn = get_db_connection()
    cursor = conn.cursor()

    print("Loading reference data from the database...")
    taxonomy_lookup = load_taxonomy_lookup(cursor)

    cursor.execute('SELECT "observationID" FROM observations;')
    valid_observation_ids = {row["observationID"] for row in cursor.fetchall()}

    cursor.execute("SELECT file_url FROM observation_media;")
    already_imported = {row["file_url"] for row in cursor.fetchall()}

    print(f"  {len(taxonomy_lookup)} taxon names, {len(valid_observation_ids)} observations, "
          f"{len(already_imported)} photos already catalogued.\n")

    needs_attention_rows = []
    ambiguous_default_rows = []
    to_insert = []  # (link_level, observation_id, taxon_id, file_url, caption)

    def handle_specimen_folder(folder_path, nearest_taxon_id, breadcrumb):
        folder_name = os.path.basename(folder_path)
        images = find_images(folder_path)
        if len(images) == 0:
            return  # empty placeholder folder - nothing to do

        acres_match = ACRES_PATTERN.search(folder_name)
        link_level = None
        observation_id = None
        taxon_id = None
        reason_if_skipped = None

        if acres_match:
            candidate_obs_id = acres_match.group(1)
            if candidate_obs_id in valid_observation_ids:
                link_level = 'observation'
                observation_id = candidate_obs_id
            else:
                reason_if_skipped = f"AcReS number {candidate_obs_id} found in folder name, but no matching observationID exists in the database"
        elif nearest_taxon_id is not None:
            link_level = 'taxon'
            taxon_id = nearest_taxon_id
        else:
            reason_if_skipped = "No AcReS number found, and no resolvable taxon folder above this specimen"

        if reason_if_skipped:
            for img_path in images:
                needs_attention_rows.append({
                    'folder_path': folder_path,
                    'folder_name': folder_name,
                    'taxon_breadcrumb': breadcrumb,
                    'image_path': img_path,
                    'reason': reason_if_skipped,
                })
            return

        for img_path in images:
            rel_path = os.path.relpath(img_path, ARCHIVE_ROOT)
            if rel_path in already_imported:
                continue  # already catalogued in a previous run
            to_insert.append((link_level, observation_id, taxon_id, rel_path, folder_name))

    def walk_taxon_folder(folder_path, nearest_taxon_id, breadcrumb):
        try:
            entries = sorted(os.listdir(folder_path))
        except (PermissionError, FileNotFoundError) as e:
            print(f"  WARNING: could not read folder, skipping: {folder_path} ({e})")
            return

        for entry in entries:
            full_path = os.path.join(folder_path, entry)
            if not os.path.isdir(full_path):
                continue

            kind, rank, raw_name = parse_taxon_folder(entry)

            if kind in ('ranked', 'undet'):
                candidate_name = raw_name
                resolved_id = resolve_taxon_folder_name(candidate_name, taxonomy_lookup, ambiguous_default_rows)
                # If this folder resolves, it becomes the new "nearest known taxon"
                # for anything beneath it. If it DOESN'T resolve, we deliberately
                # do NOT fall back to the previous ancestor - specimens under an
                # unresolved folder are flagged, not silently attached one level up.
                next_nearest = resolved_id if resolved_id is not None else None
                label = candidate_name if kind == 'ranked' else f"Undet_{candidate_name}"
                walk_taxon_folder(full_path, next_nearest, f"{breadcrumb} > {label}")
            else:
                handle_specimen_folder(full_path, nearest_taxon_id, breadcrumb)

    print("Walking the archive and working out photo links (this may take a while)...")
    walk_taxon_folder(ARCHIVE_ROOT, None, "")

    print(f"\nFound {len(to_insert)} new photos to catalogue.")
    print(f"Found {len(needs_attention_rows)} photos that need attention before they can be catalogued.")
    print(f"Applied an 'accepted name' default in {len(ambiguous_default_rows)} ambiguous taxon-name cases.")

    with open(NEEDS_ATTENTION_REPORT, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['folder_path', 'folder_name', 'taxon_breadcrumb', 'image_path', 'reason'])
        writer.writeheader()
        writer.writerows(needs_attention_rows)

    with open(AMBIGUOUS_DEFAULT_REPORT, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['candidate_name', 'chosen_taxonID', 'all_matching_taxonIDs'])
        writer.writeheader()
        writer.writerows(ambiguous_default_rows)

    if args.dry_run:
        print("\n--dry-run was set: NO changes have been made to the database.")
        with open(INSERTED_REPORT, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['link_level', 'observation_id', 'taxon_id', 'file_url', 'caption'])
            writer.writerows(to_insert)
        print(f"A preview of what WOULD be inserted has been written to {INSERTED_REPORT}")
        cursor.close()
        conn.close()
        return

    print("\nInserting photo records into the database...")
    insert_sql = """
        INSERT INTO observation_media
            (link_level, observation_id, taxon_id, file_url, caption, media_type)
        VALUES (%s, %s, %s, %s, %s, 'photo');
    """
    batch = [(row[0], row[1], row[2], row[3], row[4]) for row in to_insert]
    cursor.executemany(insert_sql, batch)
    conn.commit()

    print(f"Done. Inserted {len(batch)} new photo records.")
    cursor.close()
    conn.close()


if __name__ == "__main__":
    main()
