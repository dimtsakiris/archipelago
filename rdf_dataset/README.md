# Archipelago Knowledge Base — Open RDF Dataset

Metadata of the Archipelago Network Wikibase ("Digital Cyclades": Amorgos fishing heritage + *Mining in the Cyclades*) as RDF.

Μεταδεδομένα του Wikibase του Archipelago Network (Αμοργός + Εξόρυξη στις Κυκλάδες) σε μορφή RDF / Knowledge Graph.

| File | Content |
|---|---|
| `archipelago_sample.ttl` / `.jsonld` | **Sample: 1 item per collection** (19 items) + all 19 collections + dataset description |
| `archipelago_full.ttl` / `.nt` / `.jsonld` | Full dump of all items with a known Q-ID (282 items, 19 collections) |
| `sample_items.csv` | Which item represents each collection |
| `skipped_no_qid.txt` | Items whose Q-ID is not yet confirmed (24, Amorgos, re-created items) |
| `example_queries.rq` | SPARQL queries valid on both the live endpoint and the dump |

## Model
- Subjects/predicates use the **live Wikibase URIs** (`wd:Q486`, `wdt:P3` …), so queries are portable between the endpoint and the dump.
- Each item also carries standard vocabularies: Dublin Core Terms (`dcterms:title/creator/created/spatial/isPartOf`), schema.org (`schema:ImageObject`, `VideoObject`, `AudioObject`, `contentUrl`), SKOS (`skos:note`), PROV, DCAT/VoID.
- Every `wdt:Pn` is declared as `rdfs:subPropertyOf` its standard equivalent (see top of the `.ttl` file).
- Dates are `xsd:gYear`; approximate dates keep the original text in `wdt:P11`.
- Collections are `dcmitype:Collection` and `dcat:Dataset`; labels are bilingual (`@el`, `@en`; Amorgos is Greek only).

## Access
- **Live SPARQL endpoint:** https://archipelago-wikibase.wikibase.cloud/query/sparql
- **Offline:** load `archipelago_full.ttl` in Apache Jena Fuseki, GraphDB, Oxigraph, or `rdflib`.
- **Licence:** CC BY 4.0 (check per-collection rights with donors before public release).

## Regenerate
```
python scripts/build_rdf.py \
  --amorgos-items am/items_clean.csv --amorgos-collections am/collections_clean.csv \
  --mining-items mi/items_clean.csv --mining-collections mi/collections_clean.csv \
  --mining-qids query__2_.csv --amorgos-batch batches/.../batch3a_backfill_identifiers.qs \
  --extra-qids all_ids.csv --out-dir rdf_dataset
```
To include the 24 skipped items run in the Query Service
`SELECT ?item ?id WHERE { ?item wdt:P1 wd:Q1 ; wdt:P14 ?id }`, download as CSV and pass it as `--extra-qids`.
