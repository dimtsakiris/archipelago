"""
extract_to_clean_csv.py
========================
Stage 1 of the ingestion pipeline. Reads a source Excel workbook (in
either of the two known template shapes this project has used) and
writes it out as items_clean.csv / collections_clean.csv in one
canonical schema, so that build_import.py (Stage 2) only ever has to
know about ONE input format, no matter how the source spreadsheet is
laid out.

Supported source shapes
------------------------
1. "amorgos"  — single-language (Greek) ITEM/COLLECTION workbook, the
   original Digital Cyclades Amorgos template.
2. "bilingual" — a matched pair of workbooks (Greek + English) with
   identical row order/identifiers, the Mining in the Cyclades
   template. Adds title_en/description_en, source_url, digital_type.

Canonical output schema (items_clean.csv)
------------------------------------------
identifier, title, title_en, creator, description, description_en,
date, place, keywords, an_project, color, method, collection_title,
notes, registration_date, documenter, source_url, digital_type

Canonical output schema (collections_clean.csv)
-------------------------------------------------
identifier, title, title_en, creator, description, description_en,
keywords, an_project, method, registration_date, documenter, notes

Any column not present in a given source format is simply left blank
in the canonical CSV — build_import.py already treats blank fields as
"nothing to write" for that property.

Usage
-----
    # Amorgos-style single-language workbook
    python extract_to_clean_csv.py amorgos \
        --file source.xlsx --out-dir .

    # Bilingual workbook pair (Greek + English)
    python extract_to_clean_csv.py bilingual \
        --file-el source_greek.xlsx --file-en source_english.xlsx \
        --out-dir .
"""

import argparse
import csv
import re
import sys
from pathlib import Path

import openpyxl

CANONICAL_ITEM_FIELDS = [
    "identifier", "title", "title_en", "creator", "description", "description_en",
    "date", "place", "keywords", "an_project", "color", "method",
    "collection_title", "notes", "registration_date", "documenter",
    "source_url", "digital_type",
]

CANONICAL_COLLECTION_FIELDS = [
    "identifier", "title", "title_en", "creator", "description", "description_en",
    "keywords", "an_project", "method", "registration_date", "documenter", "notes",
]


def _rows(ws, start_row=3):
    """Yield non-empty data rows from a worksheet as tuples, skipping header rows."""
    for r in range(start_row, ws.max_row + 1):
        row = list(ws.iter_rows(min_row=r, max_row=r, values_only=True))[0]
        if row and row[1] is not None:
            yield row


def _clean(val):
    if val is None:
        return ""
    return str(val).strip()


# ---------------------------------------------------------------------------
# Extractor: "amorgos" — single-language source
# ---------------------------------------------------------------------------
def extract_amorgos(file_path):
    """
    Expected ITEM columns (0-indexed, after the leading blank col0):
    1 id, 2 identifier, 3 title, 4 creator, 5 description, 6 date, 7 place,
    8 geo, 9 ekt_type, 10 digital_type, 11 europeana_type, 12 file_type,
    13 language, 14 keywords, 15 an_project, 16 color, 17 method,
    18 collection_title, 19 notes, 20 registration_date, 21 documenter,
    22 collection_slug

    Note: some exports of this template mislabel column 6's header as
    "Περιγραφή αντικειμένου" (a copy-paste artefact) even though it holds
    the date — this extractor reads by fixed position for this format,
    matching the confirmed layout, not by (unreliable) header text.
    """
    wb = openpyxl.load_workbook(file_path, data_only=True)
    ws_i = wb["ITEM"]
    ws_c = wb["COLLECTION"]

    items = []
    for row in _rows(ws_i):
        items.append({
            "identifier": _clean(row[2]),
            "title": _clean(row[3]),
            "title_en": "",
            "creator": _clean(row[4]),
            "description": _clean(row[5]),
            "description_en": "",
            "date": row[6],  # keep raw (may be float year or "g. XXXX" string)
            "place": _clean(row[7]),
            "keywords": _clean(row[14]) if len(row) > 14 else "",
            "an_project": _clean(row[15]) if len(row) > 15 else "",
            "color": _clean(row[16]) if len(row) > 16 else "",
            "method": _clean(row[17]) if len(row) > 17 else "",
            "collection_title": _clean(row[18]) if len(row) > 18 else "",
            "notes": _clean(row[19]) if len(row) > 19 else "",
            "registration_date": _clean(row[20]) if len(row) > 20 else "",
            "documenter": _clean(row[21]) if len(row) > 21 else "",
            "source_url": "",
            "digital_type": "",
        })

    collections = []
    for row in _rows(ws_c):
        collections.append({
            "identifier": _clean(row[1]),
            "title": _clean(row[2]),
            "title_en": "",
            "creator": _clean(row[3]) if len(row) > 3 else "",
            "description": _clean(row[4]) if len(row) > 4 else "",
            "description_en": "",
            "keywords": _clean(row[5]) if len(row) > 5 else "",
            "an_project": _clean(row[6]) if len(row) > 6 else "",
            "method": _clean(row[7]) if len(row) > 7 else "",
            "registration_date": _clean(row[8]) if len(row) > 8 else "",
            "documenter": _clean(row[9]) if len(row) > 9 else "",
            "notes": _clean(row[10]) if len(row) > 10 else "",
        })

    return items, collections


# ---------------------------------------------------------------------------
# Extractor: "bilingual" — matched Greek + English workbook pair
# ---------------------------------------------------------------------------
def extract_bilingual(file_el, file_en):
    """
    Expected ITEM columns (0-indexed):
    1 id, 2 identifier, 3 title, 4 creator, 5 description, 6 date, 7 place,
    8 geo, 9 ekt_type, 10 digital_type, 11 europeana_type, 12 file_type,
    13 language, 14 keywords, 15 an_project, 16 color, 17 method,
    18 collection_title, 19 notes, 20 registration_date, 21 documenter,
    22 source_url

    Expected COLLECTION columns (0-indexed):
    1 identifier, 2 title, 3 creator, 4 description, 5 keywords,
    6 an_project, 7 method, 8 registration_date, 9 documenter, 10 notes

    The English workbook is assumed row-aligned with the Greek one by
    identifier (verified below) — only title/description are taken from
    the English file; every other field comes from the Greek source.
    """
    wb_el = openpyxl.load_workbook(file_el, data_only=True)
    wb_en = openpyxl.load_workbook(file_en, data_only=True)

    ws_i_el, ws_i_en = wb_el["ITEM"], wb_en["ITEM"]
    ws_c_el, ws_c_en = wb_el["COLLECTION"], wb_en["COLLECTION"]

    rows_i_el = list(_rows(ws_i_el))
    rows_i_en = list(_rows(ws_i_en))
    rows_c_el = list(_rows(ws_c_el))
    rows_c_en = list(_rows(ws_c_en))

    if len(rows_i_el) != len(rows_i_en):
        raise ValueError(
            f"Greek/English ITEM row count mismatch: {len(rows_i_el)} vs {len(rows_i_en)}"
        )
    for a, b in zip(rows_i_el, rows_i_en):
        if _clean(a[2]) != _clean(b[2]):
            raise ValueError(f"Identifier mismatch: {a[2]!r} vs {b[2]!r}")

    items = []
    for el, en in zip(rows_i_el, rows_i_en):
        items.append({
            "identifier": _clean(el[2]),
            "title": _clean(el[3]),
            "title_en": _clean(en[3]),
            "creator": _clean(el[4]),
            "description": _clean(el[5]),
            "description_en": _clean(en[5]),
            "date": el[6],
            "place": _clean(el[7]),
            "keywords": _clean(el[14]) if len(el) > 14 else "",
            "an_project": _clean(el[15]) if len(el) > 15 else "",
            "color": _clean(el[16]) if len(el) > 16 else "",
            "method": _clean(el[17]) if len(el) > 17 else "",
            "collection_title": _clean(el[18]) if len(el) > 18 else "",
            "notes": _clean(el[19]) if len(el) > 19 else "",
            "registration_date": _clean(el[20]) if len(el) > 20 else "",
            "documenter": _clean(el[21]) if len(el) > 21 else "",
            "source_url": _clean(el[22]) if len(el) > 22 else "",
            "digital_type": _clean(el[10]) if len(el) > 10 else "",
        })

    if len(rows_c_el) != len(rows_c_en):
        raise ValueError(
            f"Greek/English COLLECTION row count mismatch: {len(rows_c_el)} vs {len(rows_c_en)}"
        )

    collections = []
    for el, en in zip(rows_c_el, rows_c_en):
        collections.append({
            "identifier": _clean(el[2]),
            "title": _clean(el[3]),
            "title_en": _clean(en[3]) if len(en) > 3 else "",
            "creator": _clean(el[4]) if len(el) > 4 else "",
            "description": _clean(el[5]) if len(el) > 5 else "",
            "description_en": _clean(en[5]) if len(en) > 5 else "",
            "keywords": _clean(el[6]) if len(el) > 6 else "",
            "an_project": _clean(el[7]) if len(el) > 7 else "",
            "method": _clean(el[8]) if len(el) > 8 else "",
            "registration_date": _clean(el[9]) if len(el) > 9 else "",
            "documenter": _clean(el[10]) if len(el) > 10 else "",
            "notes": _clean(el[11]) if len(el) > 11 else "",
        })

    return items, collections


def write_csv(rows, fields, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fields})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="format", required=True)

    p_amorgos = sub.add_parser("amorgos", help="Single-language (Greek) source workbook")
    p_amorgos.add_argument("--file", required=True)
    p_amorgos.add_argument("--out-dir", default=".")

    p_bi = sub.add_parser("bilingual", help="Matched Greek+English workbook pair")
    p_bi.add_argument("--file-el", required=True)
    p_bi.add_argument("--file-en", required=True)
    p_bi.add_argument("--out-dir", default=".")

    args = ap.parse_args()

    if args.format == "amorgos":
        items, collections = extract_amorgos(args.file)
    else:
        items, collections = extract_bilingual(args.file_el, args.file_en)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    write_csv(items, CANONICAL_ITEM_FIELDS, out_dir / "items_clean.csv")
    write_csv(collections, CANONICAL_COLLECTION_FIELDS, out_dir / "collections_clean.csv")

    print(f"✅ Wrote {len(items)} items -> {out_dir / 'items_clean.csv'}")
    print(f"✅ Wrote {len(collections)} collections -> {out_dir / 'collections_clean.csv'}")


if __name__ == "__main__":
    main()
