#!/usr/bin/env python3
"""
build_rdf.py — Archipelago Wikibase  ->  RDF / Knowledge Graph
================================================================
Transforms the project's canonical clean CSVs (output of
extract_to_clean_csv.py) into an open RDF dataset:

  * the SAME entity/property URIs as the live Wikibase
    (wd:Q486, wdt:P3 ...), so every query written against the live
    SPARQL endpoint also works on the offline dump;
  * plus standard vocabularies (Dublin Core, schema.org, DCAT, SKOS,
    PROV, VoID) so the data is interoperable and self-describing;
  * a sample (1 item per collection, 19 total) and a full dump;
  * a DCAT/VoID description that points at the live SPARQL endpoint.

Q-ID resolution
---------------
RDF subjects must be the real Q-IDs. They come from:
  * mining items      -> --mining-qids   (CSV: item,id  — SPARQL export)
  * Amorgos items     -> --amorgos-batch (batch3a_backfill_identifiers.qs)
                         + optional --extra-qids (CSV: item,id) for items
                         that were re-created later
  * collections       -> built-in maps
Items whose Q-ID is unknown are skipped and reported (never invented).

To obtain a complete id->Q-ID export run in the Query Service:
    SELECT ?item ?id WHERE { ?item wdt:P14 ?id . ?item wdt:P1 wd:Q1 }
and pass the CSV with --extra-qids.

Usage
-----
python build_rdf.py \
   --amorgos-items am/items_clean.csv --amorgos-collections am/collections_clean.csv \
   --mining-items mi/items_clean.csv --mining-collections mi/collections_clean.csv \
   --mining-qids query__2_.csv --amorgos-batch batch3a_backfill_identifiers.qs \
   [--extra-qids query_all.csv] --out-dir dataset
"""
import argparse, csv, json, re, sys
from datetime import date
from pathlib import Path
from rdflib import Graph, Literal, Namespace, URIRef, BNode
from rdflib.namespace import RDF, RDFS, XSD, DCTERMS, SKOS, FOAF, DCAT, PROV, VOID, OWL

BASE = "https://archipelago-wikibase.wikibase.cloud"
WD = Namespace(BASE + "/entity/")
WDT = Namespace(BASE + "/prop/direct/")
SCHEMA = Namespace("https://schema.org/")
DCMI = Namespace("http://purl.org/dc/dcmitype/")
SPARQL_ENDPOINT = BASE + "/query/sparql"
DATASET_URI = URIRef(BASE + "/dataset/archipelago")
CC_BY = URIRef("https://creativecommons.org/licenses/by/4.0/")

AMORGOS_COLLECTIONS = {
    "cmt_amorgos_archival_collection_hozoviotissa": "Q3",
    "cmt_amorgos_archival_collection_ioannis i vekris": "Q4",
    "cmt_amorgos_archival_collection_skopelitis": "Q5",
}
MINING_COLLECTIONS = {
    "ecdt_collection_tinos_karageorgis": "Q438", "ecdt_collection_tinos_xenofontidis": "Q439",
    "ecdt_collection_tinos_florakis": "Q440", "ecdt_collection_tinos_alexopoulos": "Q441",
    "ecdt_collection_antiparos_sinanis": "Q442", "ecdt_collection_naxos_manolas": "Q456",
    "ecdt_collection_milos_mining_museum": "Q444", "ecdt_collection_milos_sb": "Q445",
    "ecdt_collection_milos_labor_center": "Q457", "ecdt_collection_serifos_exadactylos": "Q458",
    "ecdt_collection_serifos_dona": "Q465", "ecdt_collection_acosta_tinos": "Q460",
    "ecdt_collection_acosta_naxos": "Q461", "ecdt_collection_acosta_antiparos": "Q462",
    "ecdt_collection_acosta_serifos": "Q463", "ecdt_collection_acosta_milos": "Q464",
}
# Items re-created after the original import whose new Q-ID is certain
KNOWN_RECREATED = {"cmt_amorgos_archival_skopelitis_014": "Q429"}  # identifier -> new Q-ID

# digital_type (P16) -> DCMI type + schema.org class
TYPE_MAP = {
    "Εικόνα": (DCMI.StillImage, SCHEMA.ImageObject),
    "Βίντεο": (DCMI.MovingImage, SCHEMA.VideoObject),
    "Ήχος": (DCMI.Sound, SCHEMA.AudioObject),
    "Τρισδιάστατο μοντέλο": (DCMI.PhysicalObject, SCHEMA["3DModel"]),
}

# Property documentation: PID -> (label_el, label_en, standard-vocab equivalent)
PROPS = {
    "P1": ("είναι στιγμιότυπο", "instance of", RDF.type),
    "P2": ("Δημιουργός", "creator", DCTERMS.creator),
    "P3": ("Ημερομηνία δημιουργίας", "date of creation", DCTERMS.created),
    "P4": ("Τόπος δημιουργίας", "place of creation", DCTERMS.spatial),
    "P5": ("Μέρος συλλογής", "part of collection", DCTERMS.isPartOf),
    "P6": ("Λέξεις-κλειδιά", "keywords", SCHEMA.keywords),
    "P7": ("Χρώμα", "color", None),
    "P8": ("Μέθοδος συλλογής", "collection method", None),
    "P9": ("Ημερομηνία καταχώρησης", "registration date", DCTERMS.dateSubmitted),
    "P10": ("Τεκμηριωτής", "documenter", DCTERMS.contributor),
    "P11": ("Σημειώσεις", "notes", SKOS.note),
    "P12": ("Έργο AN", "AN project", SCHEMA.isPartOf),
    "P13": ("Ίδιο με", "same as", OWL.sameAs),
    "P14": ("Αναγνωριστικό", "identifier", DCTERMS.identifier),
    "P15": ("URL πηγής", "source URL", SCHEMA.contentUrl),
    "P16": ("Ψηφιακός τύπος", "digital type", DCTERMS.type),
}


def clean(v):
    return (v or "").strip()


def parse_date(raw):
    """-> (xsd:gYear lexical or None, approximate:bool, original text)"""
    raw = clean(str(raw) if raw is not None else "")
    if not raw:
        return None, False, ""
    approx = bool(re.match(r"^(g\.|γ\.|c\.|circa|περ\.)", raw, re.I))
    try:
        return str(int(float(raw))), False, raw
    except ValueError:
        pass
    m = re.search(r"(\d{4})", raw)
    if m:
        return m.group(1), True, raw
    return None, False, raw


def read_csv(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def qid_from_uri(u):
    return u.rsplit("/", 1)[-1]


def read_qid_csv(path):
    out = {}
    for r in read_csv(path):
        out[clean(r["id"])] = qid_from_uri(clean(r["item"]))
    return out


def read_batch3a(path, skip_failed):
    out = {}
    for ln in open(path, encoding="utf-8"):
        m = re.match(r'^(Q\d+)\|P14\|"(.+)"\s*$', ln.strip())
        if m and m.group(1) not in skip_failed:
            out[m.group(2)] = m.group(1)
    return out


# Old Q-IDs in batch3a whose item never existed (re-created under other IDs)
FAILED_OLD = {f"Q{n}" for n in
              [34, 35, 36, 39, 55, 57, 58, 60, 62, 65, 66, 72, 74, 82, 83, 99, 113,
               134, 135, 136, 137, 138, 139, 140, 149]}


def collection_key(identifier, mining):
    """item identifier -> collection identifier"""
    base = re.sub(r"_\d+$", "", identifier)
    if mining:
        return base.replace("ecdt_", "ecdt_collection_", 1)
    return base.replace("cmt_amorgos_archival_", "cmt_amorgos_archival_collection_", 1)


def lit(g, s, p, text, lang=None):
    text = clean(text)
    if text:
        g.add((s, p, Literal(text, lang=lang) if lang else Literal(text)))


def add_item(g, row, qid, coll_qid, mining):
    s = WD[qid]
    g.add((s, RDF.type, SCHEMA.CreativeWork))
    g.add((s, WDT.P1, WD.Q1))
    g.add((s, DCTERMS.type, DCMI.Collection)) if False else None
    ident = clean(row["identifier"])
    lit(g, s, WDT.P14, ident)
    lit(g, s, DCTERMS.identifier, ident)
    # labels / descriptions (bilingual where available)
    for lang, t, d in (("el", row.get("title"), row.get("description")),
                       ("en", row.get("title_en"), row.get("description_en"))):
        if clean(t):
            lit(g, s, RDFS.label, t, lang)
            lit(g, s, DCTERMS.title, t, lang)
        if clean(d) and clean(d) != clean(t):
            lit(g, s, SCHEMA.description, d, lang)
            lit(g, s, DCTERMS.description, d, lang)
    if clean(row.get("creator")):
        lit(g, s, WDT.P2, row["creator"]); lit(g, s, DCTERMS.creator, row["creator"])
    year, approx, raw = parse_date(row.get("date"))
    if year:
        g.add((s, WDT.P3, Literal(year, datatype=XSD.gYear)))
        g.add((s, DCTERMS.created, Literal(year, datatype=XSD.gYear)))
        if approx:
            lit(g, s, WDT.P11, raw); lit(g, s, SKOS.note, f"Ημερομηνία (αρχική μορφή): {raw}", "el")
    if clean(row.get("place")):
        lit(g, s, WDT.P4, row["place"]); lit(g, s, DCTERMS.spatial, row["place"])
    g.add((s, WDT.P5, WD[coll_qid])); g.add((s, DCTERMS.isPartOf, WD[coll_qid]))
    if clean(row.get("keywords")):
        lit(g, s, WDT.P6, row["keywords"])
        for kw in [k.strip() for k in row["keywords"].split(",") if k.strip()]:
            lit(g, s, SCHEMA.keywords, kw, "el")
    for pid, key in (("P7", "color"), ("P8", "method"), ("P9", "registration_date"),
                     ("P10", "documenter"), ("P12", "an_project")):
        lit(g, s, WDT[pid], row.get(key))
    if clean(row.get("documenter")):
        lit(g, s, DCTERMS.contributor, row["documenter"])
    if clean(row.get("an_project")):
        lit(g, s, SCHEMA.isPartOf, row["an_project"])
    url = clean(row.get("source_url"))
    if url:
        g.add((s, WDT.P15, URIRef(url))); g.add((s, SCHEMA.contentUrl, URIRef(url)))
    dt = clean(row.get("digital_type"))
    if dt:
        lit(g, s, WDT.P16, dt)
        if dt in TYPE_MAP:
            g.add((s, DCTERMS.type, TYPE_MAP[dt][0]))
            g.add((s, RDF.type, TYPE_MAP[dt][1]))
    elif not mining:
        g.add((s, DCTERMS.type, DCMI.StillImage)); g.add((s, RDF.type, SCHEMA.ImageObject))
    g.add((s, RDFS.seeAlso, URIRef(f"{BASE}/wiki/Item:{qid}")))
    g.add((s, SCHEMA.url, URIRef(f"{BASE}/wiki/Item:{qid}")))
    g.add((s, PROV.wasDerivedFrom, DATASET_URI))


def add_collection(g, row, qid, mining, n_items):
    s = WD[qid]
    g.add((s, RDF.type, DCMI.Collection)); g.add((s, RDF.type, DCAT.Dataset))
    g.add((s, WDT.P1, WD.Q2))
    lit(g, s, WDT.P14, row["identifier"]); lit(g, s, DCTERMS.identifier, row["identifier"])
    for lang, t, d in (("el", row.get("title"), row.get("description")),
                       ("en", row.get("title_en"), row.get("description_en"))):
        if clean(t):
            lit(g, s, RDFS.label, t, lang); lit(g, s, DCTERMS.title, t, lang)
        if clean(d) and clean(d) != clean(t):
            lit(g, s, DCTERMS.description, d, lang); lit(g, s, SCHEMA.description, d, lang)
    lit(g, s, WDT.P2, row.get("creator")); lit(g, s, DCTERMS.creator, row.get("creator"))
    if clean(row.get("keywords")):
        lit(g, s, WDT.P6, row["keywords"])
    lit(g, s, WDT.P12, row.get("an_project"))
    lit(g, s, WDT.P10, row.get("documenter"))
    g.add((s, DCTERMS.license, CC_BY))
    g.add((s, DCTERMS.isPartOf, DATASET_URI))
    g.add((s, VOID.entities, Literal(n_items, datatype=XSD.integer)))
    g.add((s, RDFS.seeAlso, URIRef(f"{BASE}/wiki/Item:{qid}")))


def add_schema_triples(g):
    for q, (el, en) in {"Q1": ("ψηφιακό αντικείμενο", "digital object"),
                        "Q2": ("συλλογή", "collection")}.items():
        g.add((WD[q], RDF.type, RDFS.Class))
        g.add((WD[q], RDFS.label, Literal(el, lang="el")))
        g.add((WD[q], RDFS.label, Literal(en, lang="en")))
    g.add((WD.Q1, RDFS.subClassOf, SCHEMA.CreativeWork))
    g.add((WD.Q2, RDFS.subClassOf, DCAT.Dataset))
    for pid, (el, en, eq) in PROPS.items():
        p = WDT[pid]
        g.add((p, RDF.type, RDF.Property))
        g.add((p, RDFS.label, Literal(el, lang="el")))
        g.add((p, RDFS.label, Literal(en, lang="en")))
        if eq is not None and eq != RDF.type:
            g.add((p, RDFS.subPropertyOf, eq))
        elif eq == RDF.type:
            g.add((p, OWL.equivalentProperty, RDF.type))


def add_dataset_description(g, n_items, n_colls, n_sample, today):
    d = DATASET_URI
    g.add((d, RDF.type, DCAT.Dataset)); g.add((d, RDF.type, VOID.Dataset))
    g.add((d, DCTERMS.title, Literal("Archipelago Knowledge Base — Digital Cyclades", lang="en")))
    g.add((d, DCTERMS.title, Literal("Βάση Γνώσης Archipelago — Ψηφιακές Κυκλάδες", lang="el")))
    g.add((d, DCTERMS.description, Literal(
        "Metadata of digital cultural-heritage objects (Amorgos fishing heritage; Mining in the "
        "Cyclades) from the Archipelago Network Wikibase, published as RDF.", lang="en")))
    g.add((d, DCTERMS.description, Literal(
        "Μεταδεδομένα ψηφιακών αντικειμένων πολιτιστικής κληρονομιάς (αλιεία Αμοργού· "
        "Εξόρυξη στις Κυκλάδες) από το Wikibase του Archipelago Network, σε μορφή RDF.", lang="el")))
    g.add((d, DCTERMS.publisher, Literal("Archipelago Network")))
    g.add((d, DCTERMS.license, CC_BY))
    g.add((d, DCTERMS.issued, Literal(today, datatype=XSD.date)))
    g.add((d, DCAT.landingPage, URIRef(BASE + "/wiki/Main_Page")))
    g.add((d, VOID.sparqlEndpoint, URIRef(SPARQL_ENDPOINT)))
    g.add((d, VOID.uriSpace, Literal(str(WD))))
    g.add((d, VOID.entities, Literal(n_items + n_colls, datatype=XSD.integer)))
    g.add((d, VOID.vocabulary, DCTERMS.uri if False else URIRef(str(DCTERMS))))
    for v in (SCHEMA, DCAT, SKOS, PROV):
        g.add((d, VOID.vocabulary, URIRef(str(v))))
    svc = URIRef(BASE + "/dataset/archipelago#sparql")
    g.add((svc, RDF.type, DCAT.DataService))
    g.add((svc, DCTERMS.title, Literal("Archipelago SPARQL endpoint", lang="en")))
    g.add((svc, DCAT.endpointURL, URIRef(SPARQL_ENDPOINT)))
    g.add((svc, DCAT.servesDataset, d))
    g.add((d, DCAT.accessService, svc))
    for name, fmt, mt in (("archipelago_full.ttl", "Turtle", "text/turtle"),
                          ("archipelago_full.nt", "N-Triples", "application/n-triples"),
                          ("archipelago_full.jsonld", "JSON-LD", "application/ld+json"),
                          ("archipelago_sample.ttl", "Turtle (sample)", "text/turtle")):
        dist = URIRef(f"{BASE}/dataset/archipelago#{name}")
        g.add((d, DCAT.distribution, dist))
        g.add((dist, RDF.type, DCAT.Distribution))
        g.add((dist, DCTERMS.title, Literal(f"{fmt}: {name}", lang="en")))
        g.add((dist, DCAT.mediaType, URIRef("https://www.iana.org/assignments/media-types/" + mt)))
        g.add((dist, DCTERMS.format, Literal(fmt)))
        g.add((dist, DCAT.downloadURL, URIRef(
            f"https://raw.githubusercontent.com/dimtsakiris/archipelago/main/rdf_dataset/{name}")))


def bind(g):
    for p, n in (("wd", WD), ("wdt", WDT), ("schema", SCHEMA), ("dcterms", DCTERMS),
                 ("dcmitype", DCMI), ("dcat", DCAT), ("skos", SKOS), ("prov", PROV),
                 ("void", VOID), ("owl", OWL), ("xsd", XSD)):
        g.bind(p, n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--amorgos-items"); ap.add_argument("--amorgos-collections")
    ap.add_argument("--mining-items"); ap.add_argument("--mining-collections")
    ap.add_argument("--mining-qids"); ap.add_argument("--amorgos-batch")
    ap.add_argument("--extra-qids"); ap.add_argument("--out-dir", default="dataset")
    a = ap.parse_args()

    qids = {}
    if a.amorgos_batch:
        qids.update(read_batch3a(a.amorgos_batch, FAILED_OLD))
    if a.amorgos_batch:
        qids.update(KNOWN_RECREATED)
    if a.mining_qids:
        qids.update(read_qid_csv(a.mining_qids))
    if a.extra_qids:
        qids.update(read_qid_csv(a.extra_qids))

    sources = []  # (collection_map, coll_rows, item_rows, mining)
    if a.amorgos_items:
        sources.append((AMORGOS_COLLECTIONS, read_csv(a.amorgos_collections), read_csv(a.amorgos_items), False))
    if a.mining_items:
        sources.append((MINING_COLLECTIONS, read_csv(a.mining_collections), read_csv(a.mining_items), True))

    full, sample = Graph(), Graph()
    for g in (full, sample):
        bind(g); add_schema_triples(g)
    skipped, n_items, picked = [], 0, 0
    sample_log = []
    for cmap, crows, irows, mining in sources:
        counts = {}
        for r in irows:
            counts[collection_key(r["identifier"], mining)] = counts.get(collection_key(r["identifier"], mining), 0) + 1
        for c in crows:
            cq = cmap[c["identifier"]]
            add_collection(full, c, cq, mining, counts.get(c["identifier"], 0))
            add_collection(sample, c, cq, mining, counts.get(c["identifier"], 0))
        done = set()
        for r in irows:
            ident = r["identifier"]
            q = qids.get(ident)
            if not q:
                skipped.append(ident); continue
            ck = collection_key(ident, mining)
            cq = cmap[ck]
            add_item(full, r, q, cq, mining); n_items += 1
            if ck not in done:   # first resolvable item of each collection = sample
                add_item(sample, r, q, cq, mining); done.add(ck); picked += 1
                sample_log.append((ck, q, ident))

    n_colls = sum(len(s[1]) for s in sources)
    today = date.today().isoformat()
    for g, ni in ((full, n_items), (sample, picked)):
        add_dataset_description(g, ni, n_colls, picked, today)

    out = Path(a.out_dir); out.mkdir(parents=True, exist_ok=True)
    full.serialize(out / "archipelago_full.ttl", format="turtle")
    full.serialize(out / "archipelago_full.nt", format="nt")
    full.serialize(out / "archipelago_full.jsonld", format="json-ld", indent=2,
                   context={"wd": str(WD), "wdt": str(WDT), "schema": str(SCHEMA),
                            "dcterms": str(DCTERMS), "rdfs": str(RDFS), "skos": str(SKOS),
                            "dcat": str(DCAT), "void": str(VOID), "prov": str(PROV)})
    sample.serialize(out / "archipelago_sample.ttl", format="turtle")
    sample.serialize(out / "archipelago_sample.jsonld", format="json-ld", indent=2,
                     context={"wd": str(WD), "wdt": str(WDT), "schema": str(SCHEMA),
                              "dcterms": str(DCTERMS), "rdfs": str(RDFS)})
    with open(out / "sample_items.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f); w.writerow(["collection", "qid", "identifier"]); w.writerows(sample_log)
    with open(out / "skipped_no_qid.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(skipped))
    print(f"full: {len(full)} triples, {n_items} items, {n_colls} collections")
    print(f"sample: {len(sample)} triples, {picked} items (1 per collection)")
    print(f"skipped (Q-ID unknown): {len(skipped)}")


if __name__ == "__main__":
    main()
