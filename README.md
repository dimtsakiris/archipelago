# Archipelago — Digital Cyclades Wikibase

Semantic knowledge base documenting the fishing heritage of Amorgos, built
on a self-hosted [Wikibase Cloud](https://archipelago-wikibase.wikibase.cloud/wiki/Main_Page)
instance, as part of an Archipelago Network internship (July–December 2026).

**Intern:** Dimitris Tsakiris · **Supervisor:** Anna Maria Sichani

- Live instance: https://archipelago-wikibase.wikibase.cloud/wiki/Main_Page (user: `DimitrisTSAKIRIS`)
- SPARQL endpoint: https://archipelago-wikibase.wikibase.cloud/query/sparql
- Full documentation: [`Archipelago_Wikibase_Documentation.docx`](./Archipelago_Wikibase_Documentation.docx)

## What's here

~150 archival photographs across three donor collections, each modelled as a
Wikibase item with a small custom property/class schema (see
`property_map.json`), imported in bulk via QuickStatements from a source
Excel workbook.

| File | What it is |
|---|---|
| `property_map.json` | The full P1–P14 property schema and top-level classes (Q1/Q2) |
| `collection_qid_map.json` | Maps each donor collection to its Q-ID, plus known data-quality notes |
| `items_clean.csv` / `collections_clean.csv` | Cleaned source data exported for import |
| `items_import.qs` / `collections_import.qs` | Generated QuickStatements batches for the original bulk import |
| `scripts/build_import.py` | Generates the `.qs` batch files from the cleaned CSVs |
| `batches/2026-08-07/` | QuickStatements batches from the 7 Aug data-integrity fix session (see that folder's README) |
| `SESSION_2026-08-07.md` | Narrative log of the 7 Aug fix session — bugs found, root causes, fixes |

## Data model (short version)

- **Q1** = digital object (ψηφιακό αντικείμενο), **Q2** = collection (συλλογή)
- **Q3 / Q4 / Q5** = the three donor collections (Hozoviotissa, Ioannis Bekris, Skopelitis)
- **P1–P13**: instance_of, creator, date, place, part_of_collection, keywords,
  color, collection_method, registration_date, documenter, notes, AN_project, same_as
- **P14** (added 7 Aug 2026): a unique **identifier** matching the source
  spreadsheet's `identifier` column — the authoritative reconciliation key.
  Every item should have exactly one, and it's the safest way to check
  whether a given source row exists in the Wikibase yet.

## Status

- ✅ Data audit, automated ingestion, SPARQL query interface — complete
- ✅ Data integrity: 150/150 source rows confirmed present, each with a
  unique `P14` identifier (7 Aug 2026 — see `SESSION_2026-08-07.md`)
- ⏳ Audio/video/3D plugin check — pending
- ⏳ API (REST/GraphQL) — pending, next milestone

## Verifying the data

```sparql
PREFIX wd: <https://archipelago-wikibase.wikibase.cloud/entity/>
PREFIX wdt: <https://archipelago-wikibase.wikibase.cloud/prop/direct/>

SELECT (COUNT(DISTINCT ?id) AS ?uniqueIdentifiers) WHERE {
  ?item wdt:P1 wd:Q1 .
  ?item wdt:P14 ?id .
}
# Expect: 150
```
