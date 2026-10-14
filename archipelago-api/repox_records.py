"""
repox_records.py — load Archipelago items as plain records and serialise them
as OAI-DC or (lite) EDM XML, for harvesting by Repox.

Two sources, same SPARQL (the RDF dump uses the same URIs as the live Wikibase):
  * "live" — the Wikibase Cloud SPARQL endpoint
  * "dump" — a local RDF file (rdf_dataset/archipelago_full.ttl), for offline tests

Used by:
  * oai.py                       (OAI-PMH endpoint, automated harvesting)
  * scripts/wikibase_to_repox.py (file export, manual / scheduled import)
"""
import os
import re
from datetime import datetime, timezone
from xml.sax.saxutils import escape, quoteattr

import httpx

BASE = "https://archipelago-wikibase.wikibase.cloud"
SPARQL_ENDPOINT = BASE + "/query/sparql"
ENTITY = BASE + "/entity/"
WIKI_ITEM = BASE + "/wiki/Item:"

DATA_PROVIDER = os.getenv("DATA_PROVIDER", "Archipelago Network")
PROVIDER = os.getenv("PROVIDER", "Archipelago Network")
# PROVISIONAL licence — confirm with the project team / donors before harvesting publicly
RIGHTS_URI = os.getenv("RIGHTS_URI", "https://creativecommons.org/licenses/by/4.0/")

# P16 digital type -> (DCMI type, EDM type)
TYPES = {
    "Εικόνα": ("StillImage", "IMAGE"),
    "Βίντεο": ("MovingImage", "VIDEO"),
    "Ήχος": ("Sound", "SOUND"),
    "Τρισδιάστατο μοντέλο": ("PhysicalObject", "3D"),
}

QUERY = """
PREFIX wd: <https://archipelago-wikibase.wikibase.cloud/entity/>
PREFIX wdt: <https://archipelago-wikibase.wikibase.cloud/prop/direct/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX schema: <@SCHEMA@>
SELECT ?item ?id ?tel ?ten ?del ?den ?creator ?date ?place ?kw ?coll ?cel ?cen ?type ?url ?mod WHERE {
  ?item wdt:P1 wd:Q1 ; wdt:P5 ?coll .
  OPTIONAL { ?item rdfs:label ?tel . FILTER(lang(?tel) = "el") }
  OPTIONAL { ?item rdfs:label ?ten . FILTER(lang(?ten) = "en") }
  OPTIONAL { ?item schema:description ?del . FILTER(lang(?del) = "el") }
  OPTIONAL { ?item schema:description ?den . FILTER(lang(?den) = "en") }
  OPTIONAL { ?item wdt:P14 ?id }
  OPTIONAL { ?item wdt:P2 ?creator }
  OPTIONAL { ?item wdt:P3 ?date }
  OPTIONAL { ?item wdt:P4 ?place }
  OPTIONAL { ?item wdt:P6 ?kw }
  OPTIONAL { ?item wdt:P16 ?type }
  OPTIONAL { ?item wdt:P15 ?url }
  OPTIONAL { ?item schema:dateModified ?mod }
  OPTIONAL { ?coll rdfs:label ?cel . FILTER(lang(?cel) = "el") }
  OPTIONAL { ?coll rdfs:label ?cen . FILTER(lang(?cen) = "en") }
}
"""


# The live Wikibase RDF uses the http:// schema.org namespace; our RDF dump uses https://
SCHEMA_LIVE, SCHEMA_DUMP = "http://schema.org/", "https://schema.org/"


def _rows_live():
    r = httpx.post(SPARQL_ENDPOINT, data={"query": QUERY.replace("@SCHEMA@", SCHEMA_LIVE)},
                   headers={"Accept": "application/sparql-results+json"}, timeout=120)
    r.raise_for_status()
    for b in r.json()["results"]["bindings"]:
        yield {k: v["value"] for k, v in b.items()}


def _rows_dump(path):
    from rdflib import Graph
    g = Graph().parse(path)
    for row in g.query(QUERY.replace("@SCHEMA@", SCHEMA_DUMP)):
        yield {k: str(v) for k, v in row.asdict().items()}


def _year(v):
    m = re.search(r"(\d{4})", v or "")
    return m.group(1) if m else None


def _iso(v, fallback):
    """Normalise to OAI UTCdatestamp YYYY-MM-DDThh:mm:ssZ."""
    if v:
        m = re.match(r"(\d{4}-\d{2}-\d{2})(?:T(\d{2}:\d{2}:\d{2}))?", v)
        if m:
            return f"{m.group(1)}T{m.group(2) or '00:00:00'}Z"
    return fallback


def load_records(source="live", dump=None):
    """Return a list of record dicts, sorted by Q-ID number."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = _rows_live() if source == "live" else _rows_dump(dump)
    out = {}
    for r in rows:
        qid = r["item"].rsplit("/", 1)[-1]
        out[qid] = {
            "qid": qid,
            "url": WIKI_ITEM + qid,
            "identifier": r.get("id"),
            "title": {"el": r.get("tel"), "en": r.get("ten")},
            "description": {"el": r.get("del"), "en": r.get("den")},
            "creator": r.get("creator"),
            "year": _year(r.get("date")),
            "place": r.get("place"),
            "keywords": [k.strip() for k in (r.get("kw") or "").split(",") if k.strip()],
            "set": r["coll"].rsplit("/", 1)[-1],
            "set_title": {"el": r.get("cel"), "en": r.get("cen")},
            "digital_type": r.get("type"),
            "source_url": r.get("url"),
            "datestamp": _iso(r.get("mod"), now),
        }
    return sorted(out.values(), key=lambda x: int(x["qid"][1:]))


def sets_of(records):
    s = {}
    for r in records:
        s[r["set"]] = r["set_title"].get("el") or r["set_title"].get("en") or r["set"]
    return s


# ------------------------------------------------------------------ XML
def _el(tag, text, lang=None):
    if not text:
        return ""
    a = f" xml:lang={quoteattr(lang)}" if lang else ""
    return f"<{tag}{a}>{escape(text)}</{tag}>"


def _langs(r):
    return [l for l in ("el", "en") if r["title"].get(l) or r["description"].get(l)]


def to_oai_dc(r):
    dctype = TYPES.get(r["digital_type"] or "Εικόνα", ("StillImage", "IMAGE"))[0]
    parts = []
    for l in ("el", "en"):
        parts.append(_el("dc:title", r["title"].get(l), l))
    for l in ("el", "en"):
        d = r["description"].get(l)
        if d and d != r["title"].get(l):
            parts.append(_el("dc:description", d, l))
    parts += [_el("dc:creator", r["creator"]), _el("dc:date", r["year"]),
              _el("dc:coverage", r["place"])]
    parts += [_el("dc:subject", k) for k in r["keywords"]]
    parts += [_el("dc:type", dctype), _el("dc:identifier", r["url"]),
              _el("dc:identifier", r["identifier"]), _el("dc:source", r["source_url"]),
              _el("dc:publisher", DATA_PROVIDER), _el("dc:rights", RIGHTS_URI)]
    parts += [_el("dc:language", l) for l in _langs(r)]
    parts.append(_el("dc:relation", r["set_title"].get("el") or r["set_title"].get("en")))
    body = "".join(p for p in parts if p)
    return ('<oai_dc:dc xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
            'xsi:schemaLocation="http://www.openarchives.org/OAI/2.0/oai_dc/ '
            'http://www.openarchives.org/OAI/2.0/oai_dc.xsd">' + body + "</oai_dc:dc>")


def to_edm(r):
    """Lite EDM. Starting point only: check against the target aggregator's
    mandatory fields / validation (Europeana requires rights, edm:type, provider...)."""
    edm_type = TYPES.get(r["digital_type"] or "Εικόνα", ("StillImage", "IMAGE"))[1]
    cho = [_el("dc:title", r["title"].get(l), l) for l in ("el", "en")]
    for l in ("el", "en"):
        d = r["description"].get(l)
        if d and d != r["title"].get(l):
            cho.append(_el("dc:description", d, l))
    cho += [_el("dc:creator", r["creator"]), _el("dcterms:created", r["year"]),
            _el("dcterms:spatial", r["place"])]
    cho += [_el("dc:subject", k) for k in r["keywords"]]
    cho += [_el("dc:identifier", r["identifier"]),
            _el("dcterms:isPartOf", r["set_title"].get("el") or r["set_title"].get("en"))]
    cho += [_el("dc:language", l) for l in _langs(r)]
    cho.append(_el("edm:type", edm_type))
    agg_uri = f"{BASE}/aggregation/{r['qid']}"
    agg = [f'<edm:aggregatedCHO rdf:resource={quoteattr(r["url"])}/>',
           _el("edm:dataProvider", DATA_PROVIDER), _el("edm:provider", PROVIDER),
           f'<edm:isShownAt rdf:resource={quoteattr(r["url"])}/>',
           f'<edm:rights rdf:resource={quoteattr(RIGHTS_URI)}/>']
    web = ""
    if r["source_url"]:
        agg.append(f'<edm:isShownBy rdf:resource={quoteattr(r["source_url"])}/>')
        web = (f'<edm:WebResource rdf:about={quoteattr(r["source_url"])}>'
               f'<edm:rights rdf:resource={quoteattr(RIGHTS_URI)}/></edm:WebResource>')
    return ('<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:edm="http://www.europeana.eu/schemas/edm/" '
            'xmlns:ore="http://www.openarchives.org/ore/terms/">'
            f'<edm:ProvidedCHO rdf:about={quoteattr(r["url"])}>' + "".join(c for c in cho if c)
            + "</edm:ProvidedCHO>"
            f'<ore:Aggregation rdf:about={quoteattr(agg_uri)}>' + "".join(a for a in agg if a)
            + "</ore:Aggregation>" + web + "</rdf:RDF>")


SERIALISERS = {"oai_dc": to_oai_dc, "edm": to_edm}
