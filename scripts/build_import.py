"""
build_import.py
================
Stage 2 of the ingestion pipeline. Reads the canonical items_clean.csv /
collections_clean.csv (produced by extract_to_clean_csv.py) and writes
ready-to-run QuickStatements V1 batch files.

Every data-integrity bug found and fixed during this project's two real
ingestion sessions (7 & 12 August 2026) is handled automatically here,
so it never has to be re-diagnosed by hand again:

  - Quoting: embedded double-quotes are converted to single quotes, not
    backslash-escaped (this QuickStatements instance corrupts labels
    that contain a literal backslash).
  - Label/description collision: if an item's description is identical
    to its title, the description is omitted (Wikibase silently fails
    the *entire* CREATE otherwise).
  - 250-character limit: any label or description over 250 characters
    is safely truncated at the last word boundary (Wikibase silently
    fails the entire CREATE otherwise); truncations are reported so a
    human can shorten the source text properly later.
  - URL values (P15) are quoted like ordinary strings — an unquoted URL
    is misread as an unrecognised type by this QuickStatements instance
    and silently fails the whole item.
  - Every item/collection gets P14 (identifier) from the very first
    CREATE — no more reconciling ambiguous duplicate titles after the
    fact.

Two-phase workflow (Q-IDs cannot be known in advance)
-------------------------------------------------------
1. Run with --step collections. Run the resulting .qs file through
   QuickStatements. Note the Q-IDs it created (via the batch report or
   Special:Contributions) and fill them into the qidmap JSON file
   (identifier -> QID).
2. Run with --step items --qidmap <that file>. Every item's P5
   (part_of_collection) link is resolved from the map.

Usage
-----
    python build_import.py --step collections \\
        --items collections_clean.csv --qidmap collection_qid_map.json \\
        --out collections_import.qs

    python build_import.py --step items \\
        --items items_clean.csv --qidmap collection_qid_map.json \\
        --out items_import.qs
"""

import argparse
import csv
import json
import re
import sys
from pathlib import Path

MAX_LABEL_LEN = 250


def qs_string(val):
    """Escape a string for QuickStatements: embedded double-quotes become
    single quotes (NOT backslash-escaped — this instance corrupts labels
    that contain a literal backslash), then the whole value is wrapped
    in double quotes."""
    val = str(val).replace('"', "'").replace("\n", " ").strip()
    return f'"{val}"'


def qs_url(val):
    """URL-datatype values must ALSO be quoted like ordinary strings on
    this QuickStatements instance — a bare URL is misread as an
    unrecognised type and silently fails the whole item."""
    return f'"{val.strip()}"'


def safe_text(val, field_label, identifier, warnings):
    """Truncate text over the 250-char Wikibase label/description limit
    at the last word boundary, logging a warning so it can be fixed
    properly in the source data later."""
    val = (val or "").strip()
    if len(val) > MAX_LABEL_LEN:
        cut = val[: MAX_LABEL_LEN - 1].rsplit(" ", 1)[0]
        warnings.append(
            f"  {identifier}: {field_label} was {len(val)} chars, truncated to {len(cut)+1}"
        )
        return cut + "…"
    return val


def parse_date(raw, identifier, warnings):
    """
    Returns (p3_commands, p11_commands) for the P3 (date) and P11 (notes)
    properties, or ([], []) if no usable date is found.

    Handles:
      - numeric year (e.g. 2015 or 2015.0)          -> year precision (/9)
      - "g. 1970" / "γ. 1970" / "c. 1970" (approx.)  -> decade precision (/8) + P11 note
      - any other string containing a 4-digit year   -> year precision (/9) + P11 note
        (keeps the original text so nothing is silently lost)
    """
    if raw is None or str(raw).strip() == "":
        return [], []

    raw_str = str(raw).strip()

    # Approximate-date markers used across both source templates
    if re.match(r"^(g\.|γ\.|c\.|circa)", raw_str, re.IGNORECASE):
        m = re.search(r"(\d{4})", raw_str)
        if not m:
            warnings.append(f"  {identifier}: could not parse approximate date {raw_str!r}")
            return [], []
        year = m.group(1)
        return (
            [f"P3|+{year}-00-00T00:00:00Z/8"],
            [f"P11|{qs_string(raw_str)}"],
        )

    # Plain numeric year (int, float-as-string, or clean 4-digit string)
    try:
        year = int(float(raw_str))
        return [f"P3|+{year}-00-00T00:00:00Z/9"], []
    except ValueError:
        pass

    # Fallback: any other string with a 4-digit year inside it
    m = re.search(r"(\d{4})", raw_str)
    if m:
        return (
            [f"P3|+{m.group(1)}-00-00T00:00:00Z/9"],
            [f"P11|{qs_string(raw_str)}"],
        )

    warnings.append(f"  {identifier}: unrecognised date format {raw_str!r}, skipped")
    return [], []


def read_clean_csv(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build_collections_qs(rows, warnings):
    lines = []
    for row in rows:
        identifier = row["identifier"]
        title = row["title"]
        if not title:
            warnings.append(f"  {identifier}: no title, skipped entirely")
            continue

        title_safe = safe_text(title, "title", identifier, warnings)
        lines.append("CREATE")
        lines.append(f"LAST|Lel|{qs_string(title_safe)}")
        if row.get("title_en"):
            lines.append(f"LAST|Len|{qs_string(safe_text(row['title_en'], 'title_en', identifier, warnings))}")
        lines.append("LAST|P1|Q2")

        desc = row.get("description", "")
        if desc and desc.strip() != title.strip():
            lines.append(f"LAST|Del|{qs_string(safe_text(desc, 'description', identifier, warnings))}")
        desc_en = row.get("description_en", "")
        if desc_en and row.get("title_en") and desc_en.strip() != row["title_en"].strip():
            lines.append(f"LAST|Den|{qs_string(safe_text(desc_en, 'description_en', identifier, warnings))}")

        if row.get("creator"):
            lines.append(f"LAST|P2|{qs_string(row['creator'])}")
        if row.get("keywords"):
            lines.append(f"LAST|P6|{qs_string(row['keywords'])}")
        if row.get("an_project"):
            lines.append(f"LAST|P12|{qs_string(row['an_project'])}")
        if row.get("documenter"):
            lines.append(f"LAST|P10|{qs_string(row['documenter'])}")
        if row.get("notes"):
            lines.append(f"LAST|P11|{qs_string(row['notes'])}")
        if identifier:
            lines.append(f"LAST|P14|{qs_string(identifier)}")

        lines.append("")

    return lines


def build_items_qs(rows, qidmap, warnings):
    lines = []
    for row in rows:
        identifier = row["identifier"]
        title = row["title"] or row.get("description") or identifier
        if not title:
            warnings.append(f"  {identifier}: no title/description/identifier at all, skipped entirely")
            continue

        title_safe = safe_text(title, "title", identifier, warnings)
        lines.append("CREATE")
        lines.append(f"LAST|Lel|{qs_string(title_safe)}")
        if row.get("title_en"):
            lines.append(f"LAST|Len|{qs_string(safe_text(row['title_en'], 'title_en', identifier, warnings))}")
        lines.append("LAST|P1|Q1")

        desc = row.get("description", "")
        if desc and desc.strip() != title.strip():
            lines.append(f"LAST|Del|{qs_string(safe_text(desc, 'description', identifier, warnings))}")
        desc_en = row.get("description_en", "")
        if desc_en and row.get("title_en") and desc_en.strip() != row["title_en"].strip():
            lines.append(f"LAST|Den|{qs_string(safe_text(desc_en, 'description_en', identifier, warnings))}")

        p3_cmds, p11_cmds = parse_date(row.get("date"), identifier, warnings)
        for c in p3_cmds:
            lines.append(f"LAST|{c}")
        for c in p11_cmds:
            lines.append(f"LAST|{c}")

        if row.get("creator"):
            lines.append(f"LAST|P2|{qs_string(row['creator'])}")
        if row.get("place"):
            lines.append(f"LAST|P4|{qs_string(row['place'])}")
        if row.get("keywords"):
            lines.append(f"LAST|P6|{qs_string(row['keywords'])}")
        if row.get("color"):
            lines.append(f"LAST|P7|{qs_string(row['color'])}")
        if row.get("method"):
            lines.append(f"LAST|P8|{qs_string(row['method'])}")
        if row.get("registration_date"):
            lines.append(f"LAST|P9|{qs_string(row['registration_date'])}")
        if row.get("documenter"):
            lines.append(f"LAST|P10|{qs_string(row['documenter'])}")
        if row.get("an_project"):
            lines.append(f"LAST|P12|{qs_string(row['an_project'])}")
        if identifier:
            lines.append(f"LAST|P14|{qs_string(identifier)}")
        if row.get("source_url"):
            lines.append(f"LAST|P15|{qs_url(row['source_url'])}")
        if row.get("digital_type"):
            lines.append(f"LAST|P16|{qs_string(row['digital_type'])}")

        coll_title = row.get("collection_title")
        if coll_title:
            coll_qid = qidmap.get(coll_title) or qidmap.get(identifier)
            if coll_qid:
                lines.append(f"LAST|P5|{coll_qid}")
            else:
                warnings.append(
                    f"  {identifier}: collection '{coll_title}' not found in qidmap — P5 link skipped"
                )

        lines.append("")

    return lines


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--step", choices=["collections", "items"], required=True)
    ap.add_argument("--items", required=True, help="Path to the canonical clean CSV (items_clean.csv or collections_clean.csv)")
    ap.add_argument("--qidmap", help="Path to collection_qid_map.json (required for --step items; a title->QID dict)")
    ap.add_argument("--out", required=True, help="Output .qs file path")
    args = ap.parse_args()

    rows = read_clean_csv(args.items)
    warnings = []

    if args.step == "collections":
        lines = build_collections_qs(rows, warnings)
    else:
        if not args.qidmap or not Path(args.qidmap).exists():
            print(f"ERROR: --step items requires --qidmap pointing to an existing collection_qid_map.json", file=sys.stderr)
            sys.exit(1)
        with open(args.qidmap, encoding="utf-8") as f:
            qidmap = json.load(f)
        lines = build_items_qs(rows, qidmap, warnings)

    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    n_blocks = sum(1 for l in lines if l == "CREATE")
    print(f"✅ Wrote {args.out} ({n_blocks} CREATE blocks from {len(rows)} source rows)")

    if warnings:
        print(f"\n⚠️  {len(warnings)} warning(s):")
        for w in warnings:
            print(w)


if __name__ == "__main__":
    main()
