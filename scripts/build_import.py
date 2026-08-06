"""Build QuickStatements import batches from Amorgos collection data."""
import argparse
import json
import re
import os
import pandas as pd

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
print("Script started! Working directory:", os.getcwd())

ITEMS_CSV = "items_clean.csv"
COLLECTIONS_CSV = "collections_clean.csv"
PROPERTY_MAP = "property_map.json"
COLLECTION_QID_MAP = "collection_qid_map.json"

def load_property_map():
    with open(PROPERTY_MAP, encoding="utf-8") as f:
        pm = json.load(f)
    return pm

def pid(pm, key):
    v = pm[key]["pid"]
    return v if v else f"P_{key.upper()}"

def qs_string(val):
    val = str(val).replace('"', "'").replace("\n", " ").strip()
    return f'"{val}"'

def parse_year(raw):
    if pd.isna(raw):
        return None
    m = re.search(r"(1[5-9]\d{2}|20[0-2]\d)", str(raw))
    return m.group(1) if m else None

def is_circa(raw):
    return bool(re.search(r"[γg]\.\s*\d", str(raw), re.IGNORECASE))

def qs_time(year):
    return f"+{year}-00-00T00:00:00Z/9"

def build_collections_qs(pm):
    df = pd.read_csv(COLLECTIONS_CSV)
    lines = []
    cls = pm["_classes"]["collection"]["qid"] or "Q_COLLECTION_CLASS"
    for _, row in df.iterrows():
        lines.append("CREATE")
        lines.append(f'LAST\tLen\t{qs_string(row["title"])}')
        desc = row["description"] if pd.notna(row.get("description")) else f'Archival photo collection: {row["title"]}'
        lines.append(f'LAST\tDen\t{qs_string(desc)}')
        lines.append(f'LAST\t{pid(pm,"instance_of")}\t{cls}')
        if pd.notna(row.get("creator")):
            lines.append(f'LAST\t{pid(pm,"creator")}\t{qs_string(row["creator"])}')
        lines.append("")

    with open("collections_import.qs", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"✅ Wrote collections_import.qs ({len(df)} collections).")

def build_items_qs(pm):
    with open(COLLECTION_QID_MAP, encoding="utf-8") as f:
        coll_map = json.load(f)
    missing = [k for k, v in coll_map.items() if v is None]
    if missing:
        raise SystemExit(f"❌ collection_qid_map.json missing QIDs for: {missing}")

    df = pd.read_csv(ITEMS_CSV)
    cls = pm["_classes"]["digital_object"]["qid"] or "Q_DIGITAL_OBJECT"
    lines = []
    for _, row in df.iterrows():
        title = row["title"] if pd.notna(row.get("title")) else str(row["description"])[:60]
        lines.append("CREATE")
        lines.append(f'LAST\tLen\t{qs_string(title)}')
        desc = row["description"] if pd.notna(row.get("description")) else title
        lines.append(f'LAST\tDen\t{qs_string(desc)}')
        lines.append(f'LAST\t{pid(pm,"instance_of")}\t{cls}')

        coll_qid = coll_map.get(row["collection_slug"])
        if coll_qid:
            lines.append(f'LAST\t{pid(pm,"part_of_collection")}\t{coll_qid}')

        if pd.notna(row.get("creator")):
            lines.append(f'LAST\t{pid(pm,"creator")}\t{qs_string(row["creator"])}')
        if pd.notna(row.get("place")):
            lines.append(f'LAST\t{pid(pm,"place_of_creation")}\t{qs_string(row["place"])}')
        if pd.notna(row.get("documenter")):
            lines.append(f'LAST\t{pid(pm,"documenter")}\t{qs_string(row["documenter"])}')

        notes_parts = []
        if pd.notna(row.get("notes")):
            notes_parts.append(str(row["notes"]))

        raw_date = row.get("date")
        if pd.notna(raw_date):
            year = parse_year(raw_date)
            if year and not is_circa(raw_date):
                lines.append(f'LAST\t{pid(pm,"date_of_creation")}\t{qs_time(year)}')
            else:
                notes_parts.append(f"[date uncertain: {raw_date}]")

        if notes_parts:
            lines.append(f'LAST\t{pid(pm,"notes")}\t{qs_string(" ; ".join(notes_parts))}')

        if pd.notna(row.get("keywords")):
            for kw in str(row["keywords"]).split(","):
                kw = kw.strip()
                if kw:
                    lines.append(f'LAST\t{pid(pm,"keywords")}\t{qs_string(kw)}')

        lines.append("")

    with open("items_import.qs", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"✅ Wrote items_import.qs ({len(df)} items).")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", choices=["collections", "items"], required=True)
    args = ap.parse_args()
    pm = load_property_map()
    if args.step == "collections":
        build_collections_qs(pm)
    else:
        build_items_qs(pm)
