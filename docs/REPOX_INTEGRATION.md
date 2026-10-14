# Wikibase → Repox integration

Repox is a metadata aggregation / harvesting framework (used in the Europeana ecosystem).
It collects records mainly through **OAI-PMH**, stores them as XML, transforms them with
**XSLT**, and can re-publish them. Wikibase has no OAI-PMH, so this repo adds the bridge.

```
Wikibase Cloud ──SPARQL──►  repox_records.py ──┬──► oai.py  (OAI-PMH endpoint, AUTOMATED)  ──► Repox harvests
(source of truth)                              └──► scripts/wikibase_to_repox.py (XML files, MANUAL / scheduled) ──► Repox imports
```

One record = one Wikibase item (Q1). One OAI set = one collection (setSpec = collection Q-ID, 19 sets).
Formats: `oai_dc` (Dublin Core, mandatory in OAI-PMH) and `edm` (lite Europeana Data Model).

## A. Manual route (works today, no server)
```
pip install httpx
python scripts/wikibase_to_repox.py --out-dir repox_export --zip            # everything
python scripts/wikibase_to_repox.py --since 2026-10-01 --out-dir repox_update # only changed items
python scripts/wikibase_to_repox.py --format edm --out-dir repox_edm
```
Output: `records/Qnnn.xml` (one file per item), `records.xml` (all in one), `records.zip`.
Give the folder/zip to Repox (folder, HTTP or FTP data source — use whichever your Repox instance offers).
`--incremental` remembers the last run in `state.json`.

A GitHub Action (`.github/workflows/repox-export.yml`) can run this weekly and commit the result to
`repox_export/`, so Repox can fetch it from a stable URL:
`https://raw.githubusercontent.com/dimtsakiris/archipelago/main/repox_export/records.xml`.

## B. Automated route (OAI-PMH)
The API serves `/oai` once deployed (e.g. Render). Test locally:
```
cd archipelago-api && python -m uvicorn main:app --reload
http://localhost:8000/oai?verb=Identify
http://localhost:8000/oai?verb=ListSets
http://localhost:8000/oai?verb=ListRecords&metadataPrefix=oai_dc
http://localhost:8000/oai?verb=ListRecords&metadataPrefix=oai_dc&from=2026-10-01     (incremental)
http://localhost:8000/oai?verb=GetRecord&identifier=oai:archipelago:Q486&metadataPrefix=edm
```
In Repox: add a Data Provider → add a Data Source of type **OAI-PMH**, URL = `<deployed api>/oai`,
metadata format `oai_dc` (or `edm`), optionally a set (a collection Q-ID); attach an XSLT if it must
become EDM; schedule the ingest (daily/weekly). Repox then does incremental harvests with `from=<last date>`.

## C. How updates flow
1. Edit/add items in Wikibase (e.g. via the QuickStatements pipeline).
2. Repox's next scheduled harvest (B) – or your next export (A) – picks up the changed items.
3. Items are identified by `oai:archipelago:<Q-ID>`; the stable key in the data is P14.

## D. Things to confirm (not verified from here)
* **Datestamps:** the endpoint uses Wikibase's `schema:dateModified`. Check it exists, in the Query Service:
  `SELECT ?i ?m WHERE { ?i <http://schema.org/dateModified> ?m } LIMIT 5`.
  If empty, every harvest looks "modified now" (still correct, but not incremental).
* **Which Repox instance/version** the team uses and which data-source types it offers (OAI-PMH is the safe one).
* **Target schema**: if records must reach Europeana, validate the `edm` output (mandatory: edm:type, edm:rights,
  edm:dataProvider, edm:provider, isShownAt/isShownBy) and agree the **rights statement** — `RIGHTS_URI`
  (default CC BY 4.0) is provisional. Set `DATA_PROVIDER`, `PROVIDER`, `RIGHTS_URI` as environment variables.
* Deleted items are not reported (the Wikibase can't delete: duplicates are only de-typed by removing P1).
* Public items only: the endpoint exposes every item with P1 = Q1.

## Configuration (env vars)
`OAI_SOURCE` live|dump · `OAI_DUMP` path to `.ttl` (offline tests) · `OAI_PAGE_SIZE` (100) ·
`OAI_CACHE_SECONDS` (600) · `DATA_PROVIDER` · `PROVIDER` · `RIGHTS_URI`
