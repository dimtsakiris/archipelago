# Ingestion pipeline (scripts/)

Two stages, so that adding or fixing data never means hand-writing
Wikibase edits.

```
raw Excel  →  extract_to_clean_csv.py  →  clean CSVs  →  build_import.py  →  .qs batch
```

## Stage 1 — `extract_to_clean_csv.py`

Normalizes a raw source workbook into a single canonical CSV schema
(`items_clean.csv` / `collections_clean.csv`), regardless of which of
the two known source template shapes it came from. This is what makes
Stage 2 reusable — it only ever has to understand one input format.

**Amorgos-style (single-language) workbook:**
```bash
python scripts/extract_to_clean_csv.py amorgos \
  --file digital_cyclades_amorgos_wikibase.xlsx \
  --out-dir .
```

**Bilingual workbook pair (Greek + English), like the Mining dataset:**
```bash
python scripts/extract_to_clean_csv.py bilingual \
  --file-el digital_cyclades_extraction_greek.xlsx \
  --file-en digital_cyclades_extraction_english.xlsx \
  --out-dir .
```

Both write `items_clean.csv` and `collections_clean.csv` in the same
canonical schema (English title/description, source URL, and digital
type columns are simply left blank when the source format doesn't have
them).

If a third template shape shows up in future, add one more `extract_*`
function following the same pattern — Stage 2 never needs to change.

## Stage 2 — `build_import.py`

Reads the canonical clean CSVs and writes ready-to-run QuickStatements
V1 batch files. Every data-integrity bug found during this project's
two real ingestion sessions is fixed here automatically:

- Quoting: embedded `"` → `'`, never backslash-escaped.
- Skips a description that's identical to the title (Wikibase silently
  fails the *entire* CREATE otherwise).
- Auto-truncates any label/description over the 250-character Wikibase
  limit at a word boundary, and prints a warning so the source text can
  be shortened properly later.
- Quotes URL-datatype values (P15) like ordinary strings.
- Every item/collection gets P14 (identifier) from the very first
  CREATE.

**Step 1 — collections** (run this first; Q-IDs can't be predicted in
advance):
```bash
python scripts/build_import.py --step collections \
  --items collections_clean.csv \
  --out collections_import.qs
```
Run `collections_import.qs` through QuickStatements, note the Q-IDs it
created (via the batch report or Special:Contributions), and build a
JSON map of `{"<collection title>": "<Q-ID>"}` — save it as e.g.
`collection_qid_map.json`.

**Step 2 — items:**
```bash
python scripts/build_import.py --step items \
  --items items_clean.csv \
  --qidmap collection_qid_map.json \
  --out items_import.qs
```

The script prints how many CREATE blocks it wrote and lists any
warnings (truncated text, unresolved collection links, skipped rows
with no title) so problems are visible before you ever touch
QuickStatements.

## Tested against real project data

Both extractors and both build steps have been run against the actual
150-item Amorgos dataset and the actual 156-item / 16-collection Mining
in the Cyclades dataset, producing output verified against what was
manually confirmed to work in Wikibase during the 7 & 12 August 2026
sessions — including the 250-character auto-truncation correctly
catching the two collection descriptions that caused failures during
the original manual run.
