# Archipelago Knowledge Base — Open RDF Dataset

Metadata of the Archipelago Network Wikibase ("Digital Cyclades": Amorgos fishing heritage + *Mining in the Cyclades*) as RDF.

Μεταδεδομένα του Wikibase του Archipelago Network (Αμοργός + Εξόρυξη στις Κυκλάδες) σε μορφή RDF / Knowledge Graph.

| File | Content |
|---|---|
| `archipelago_sample.ttl` / `.jsonld` | **Sample: 1 item per collection** (19 items) + all 19 collections + dataset description |
| `archipelago_full.ttl` / `.nt` / `.jsonld` | Full dump: all 306 items and 19 collections |
| `sample_items.csv` | Which item represents each collection |
| `qid_map.csv` | identifier (P14) → Q-ID map exported from the Query Service (322 rows) |
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
  --extra-qids rdf_dataset/qid_map.csv --out-dir rdf_dataset
```
Refresh `qid_map.csv` with this query (full URIs; the UI's `wdt:` prefix may return 0):
`SELECT ?item ?id WHERE { ?item <https://archipelago-wikibase.wikibase.cloud/prop/direct/P14> ?id }`
