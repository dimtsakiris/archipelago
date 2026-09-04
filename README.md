# Archipelago — Digital Cyclades Wikibase

Semantic knowledge base on a self-hosted [Wikibase Cloud](https://archipelago-wikibase.wikibase.cloud/wiki/Main_Page)
instance, built as part of an Archipelago Network internship (July–December 2026).
Now spans **two** collections: the original Amorgos fishing-heritage archive and
the newer Mining in the Cyclades: Digital Traces archive.

**Intern:** Dimitris Tsakiris · **Supervisor:** Anna Maria Sichani

- Live instance: https://archipelago-wikibase.wikibase.cloud/wiki/Main_Page (user: `DimitrisTSAKIRIS`)
- SPARQL endpoint: https://archipelago-wikibase.wikibase.cloud/query/
- REST API: see [`archipelago-api/`](./archipelago-api/) — run locally or deploy to the cloud
- Full documentation: [`Archipelago_Wikibase_Documentation.docx`](./Archipelago_Wikibase_Documentation.docx)

**Current totals: 306 digital objects, 19 collections.**

## What's here

| File / folder | What it is |
|---|---|
| `property_map.json` | The full P1–P16 property schema and top-level classes (Q1/Q2) |
| `collection_qid_map.json` | Amorgos collection slug → Q-ID mapping |
| `mining_collection_qid_map.json` | Mining-dataset collection slug → Q-ID mapping |
| `items_clean.csv` / `collections_clean.csv` | Cleaned source data for the Amorgos import |
| `items_import.qs` / `collections_import.qs` | Generated QuickStatements batches for the Amorgos import |
| `scripts/build_import.py` | Generates `.qs` batch files from cleaned CSVs |
| `batches/2026-08-07/` | QuickStatements batches from the 7 Aug data-integrity fix session (see that folder's README) |
| `SESSION_2026-08-07.md` | Narrative log of the 7 Aug fix session — bugs found, root causes, fixes |
| `sparql-interface.html` | Standalone SPARQL query tool with pre-built templates |
| `archipelago-api/` | REST API (FastAPI) wrapping the SPARQL endpoint — see its own README for run/deploy instructions |

## Data model (short version)

- **Q1** = digital object, **Q2** = collection
- **Q3 / Q4 / Q5** = the three Amorgos donor collections (Hozoviotissa, Ioannis Bekris, Skopelitis)
- 16 further collections (Q438–Q465 range) hold the Mining in the Cyclades dataset,
  grouped by island (Tinos, Antiparos, Naxos, Milos, Serifos)
- **P1–P13**: instance_of, creator, date, place, part_of_collection, keywords,
  color, collection_method, registration_date, documenter, notes, AN_project, same_as
- **P14**: unique **identifier** matching the source spreadsheet — the authoritative
  reconciliation key. Every item has exactly one.
- **P15**: **source URL** — link to the actual media file (image/video/audio/3D scan).
  Used instead of native file uploads, since wikibase.cloud doesn't currently bundle
  audio/video/3D extensions (see the docs, §8).
- **P16**: **digital object type** (Εικόνα / Βίντεο / Ήχος / 3D) for filtering.

## REST API

A FastAPI app in [`archipelago-api/`](./archipelago-api/) exposes the whole
Wikibase as clean JSON — no SPARQL required.

```bash
cd archipelago-api
pip install -r requirements.txt
python -m uvicorn main:app --reload
# open http://localhost:8000/docs
```

Endpoints: `/items`, `/items/{qid}`, `/collections`, `/collections/{qid}`,
`/search?q=...`, `/stats`. Full details, filter options, and cloud deployment
instructions (Render.com / Railway / Fly.io) are in `archipelago-api/README.md`.

## Status

- ✅ Data audit, automated ingestion, SPARQL query interface — complete
- ✅ Data integrity: 150/150 Amorgos items confirmed, unique P14 identifiers (7 Aug 2026)
- ✅ Audio/video/3D support — resolved via external-URL property P15 (12 Aug 2026)
- ✅ Mining in the Cyclades dataset — 156 items, 16 collections (12 Aug 2026)
- ✅ REST API — working locally (17 Aug 2026)
- ⏳ Cloud deployment of the API — next step

## Verifying the data

```sparql
PREFIX wd: <https://archipelago-wikibase.wikibase.cloud/entity/>
PREFIX wdt: <https://archipelago-wikibase.wikibase.cloud/prop/direct/>

SELECT (COUNT(?item) AS ?count) WHERE {
  ?item wdt:P1 wd:Q1 .
}
# Expect: 306
```