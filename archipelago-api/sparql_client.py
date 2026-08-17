"""
SPARQL client for the Archipelago Wikibase instance.

Centralises the property/class ID mapping so the rest of the API never
has to know that "creator" is P2 or that "digital object" is Q1 — that
mapping lives in exactly one place (PROPS / CLASSES below) and should be
updated here if the schema changes in property_map.json.
"""

import httpx
from typing import Optional

SPARQL_ENDPOINT = "https://archipelago-wikibase.wikibase.cloud/query/sparql"
ENTITY_PREFIX = "https://archipelago-wikibase.wikibase.cloud/entity/"
PROP_PREFIX = "https://archipelago-wikibase.wikibase.cloud/prop/direct/"

# Property ID -> friendly JSON key
PROPS = {
    "P1": "instance_of",
    "P2": "creator",
    "P3": "date",
    "P4": "place",
    "P5": "collection",
    "P6": "keywords",
    "P7": "color",
    "P8": "collection_method",
    "P9": "registration_date",
    "P10": "documenter",
    "P11": "notes",
    "P12": "an_project",
    "P13": "same_as",
    "P14": "identifier",
    "P15": "source_url",
    "P16": "digital_object_type",
}

CLASS_DIGITAL_OBJECT = "Q1"
CLASS_COLLECTION = "Q2"

HEADERS = {"Accept": "application/sparql-results+json"}


def _qid_from_uri(uri: str) -> str:
    """https://.../entity/Q123 -> Q123"""
    return uri.rsplit("/", 1)[-1]


async def _run_query(query: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            SPARQL_ENDPOINT, params={"query": query}, headers=HEADERS
        )
        resp.raise_for_status()
        data = resp.json()
        return data["results"]["bindings"]


def _binding_value(binding: dict, key: str) -> Optional[str]:
    if key in binding:
        return binding[key]["value"]
    return None


def _escape_literal(value: str) -> str:
    """Escape a string for safe embedding in a SPARQL string literal."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


async def get_item(qid: str, lang: str = "el") -> Optional[dict]:
    simple_query = f"""
    PREFIX wd: <{ENTITY_PREFIX}>
    PREFIX wdt: <{PROP_PREFIX}>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX schema: <http://schema.org/>
    SELECT ?labelEl ?labelEn ?descEl ?descEn {" ".join(f"?{v}" for v in PROPS.values())} WHERE {{
      OPTIONAL {{ wd:{qid} rdfs:label ?labelEl . FILTER(LANG(?labelEl) = "el") }}
      OPTIONAL {{ wd:{qid} rdfs:label ?labelEn . FILTER(LANG(?labelEn) = "en") }}
      OPTIONAL {{ wd:{qid} schema:description ?descEl . FILTER(LANG(?descEl) = "el") }}
      OPTIONAL {{ wd:{qid} schema:description ?descEn . FILTER(LANG(?descEn) = "en") }}
      {"".join(f'OPTIONAL {{ wd:{qid} wdt:{p} ?{v} . }} ' for p, v in PROPS.items())}
    }}
    """
    rows = await _run_query(simple_query)
    if not rows:
        return None
    b = rows[0]

    result = {
        "id": qid,
        "label": {
            "el": _binding_value(b, "labelEl"),
            "en": _binding_value(b, "labelEn"),
        },
        "description": {
            "el": _binding_value(b, "descEl"),
            "en": _binding_value(b, "descEn"),
        },
    }
    for p, key in PROPS.items():
        val = _binding_value(b, key)
        if val and val.startswith(ENTITY_PREFIX):
            val = _qid_from_uri(val)
        result[key] = val
    return result


async def list_items(
    lang: str = "el",
    collection: Optional[str] = None,
    creator: Optional[str] = None,
    place: Optional[str] = None,
    an_project: Optional[str] = None,
    digital_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    filters = []
    if collection:
        filters.append(f"?item wdt:P5 wd:{collection} .")
    if creator:
        filters.append(f'?item wdt:P2 "{_escape_literal(creator)}" .')
    if place:
        filters.append(f'?item wdt:P4 "{_escape_literal(place)}" .')
    if an_project:
        filters.append(f'?item wdt:P12 "{_escape_literal(an_project)}" .')
    if digital_type:
        filters.append(f'?item wdt:P16 "{_escape_literal(digital_type)}" .')
    filter_clause = "\n      ".join(filters)

    query = f"""
    PREFIX wd: <{ENTITY_PREFIX}>
    PREFIX wdt: <{PROP_PREFIX}>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    SELECT ?item ?label ?identifier WHERE {{
      ?item wdt:P1 wd:{CLASS_DIGITAL_OBJECT} .
      {filter_clause}
      OPTIONAL {{ ?item rdfs:label ?label . FILTER(LANG(?label) = "{lang}") }}
      OPTIONAL {{ ?item wdt:P14 ?identifier . }}
    }}
    ORDER BY ?item
    LIMIT {limit}
    OFFSET {offset}
    """
    rows = await _run_query(query)
    items = [
        {
            "id": _qid_from_uri(_binding_value(r, "item")),
            "label": _binding_value(r, "label"),
            "identifier": _binding_value(r, "identifier"),
        }
        for r in rows
    ]
    return {"count": len(items), "limit": limit, "offset": offset, "items": items}


async def search_items(q: str, lang: str = "el", limit: int = 50) -> dict:
    q_escaped = _escape_literal(q)
    query = f"""
    PREFIX wd: <{ENTITY_PREFIX}>
    PREFIX wdt: <{PROP_PREFIX}>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    SELECT ?item ?label WHERE {{
      ?item wdt:P1 wd:{CLASS_DIGITAL_OBJECT} .
      ?item rdfs:label ?label .
      FILTER(LANG(?label) = "{lang}")
      FILTER(CONTAINS(LCASE(?label), LCASE("{q_escaped}")))
    }}
    LIMIT {limit}
    """
    rows = await _run_query(query)
    items = [
        {"id": _qid_from_uri(_binding_value(r, "item")), "label": _binding_value(r, "label")}
        for r in rows
    ]
    return {"query": q, "count": len(items), "items": items}


async def list_collections(lang: str = "el") -> dict:
    query = f"""
    PREFIX wd: <{ENTITY_PREFIX}>
    PREFIX wdt: <{PROP_PREFIX}>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    SELECT ?coll ?label (COUNT(?item) AS ?itemCount) WHERE {{
      ?coll wdt:P1 wd:{CLASS_COLLECTION} .
      OPTIONAL {{ ?coll rdfs:label ?label . FILTER(LANG(?label) = "{lang}") }}
      OPTIONAL {{ ?item wdt:P5 ?coll . }}
    }}
    GROUP BY ?coll ?label
    ORDER BY ?coll
    """
    rows = await _run_query(query)
    colls = [
        {
            "id": _qid_from_uri(_binding_value(r, "coll")),
            "label": _binding_value(r, "label"),
            "item_count": int(_binding_value(r, "itemCount") or 0),
        }
        for r in rows
    ]
    return {"count": len(colls), "collections": colls}


async def get_collection(qid: str, lang: str = "el") -> Optional[dict]:
    meta_query = f"""
    PREFIX wd: <{ENTITY_PREFIX}>
    PREFIX wdt: <{PROP_PREFIX}>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX schema: <http://schema.org/>
    SELECT ?label ?descEl ?descEn ?creator ?an_project ?documenter WHERE {{
      wd:{qid} wdt:P1 wd:{CLASS_COLLECTION} .
      OPTIONAL {{ wd:{qid} rdfs:label ?label . FILTER(LANG(?label) = "{lang}") }}
      OPTIONAL {{ wd:{qid} schema:description ?descEl . FILTER(LANG(?descEl)="el") }}
      OPTIONAL {{ wd:{qid} schema:description ?descEn . FILTER(LANG(?descEn)="en") }}
      OPTIONAL {{ wd:{qid} wdt:P2 ?creator . }}
      OPTIONAL {{ wd:{qid} wdt:P12 ?an_project . }}
      OPTIONAL {{ wd:{qid} wdt:P10 ?documenter . }}
    }}
    """
    meta_rows = await _run_query(meta_query)
    if not meta_rows:
        return None
    m = meta_rows[0]

    items_result = await list_items(lang=lang, collection=qid, limit=500, offset=0)

    return {
        "id": qid,
        "label": _binding_value(m, "label"),
        "description": {
            "el": _binding_value(m, "descEl"),
            "en": _binding_value(m, "descEn"),
        },
        "creator": _binding_value(m, "creator"),
        "an_project": _binding_value(m, "an_project"),
        "documenter": _binding_value(m, "documenter"),
        "item_count": items_result["count"],
        "items": items_result["items"],
    }


async def get_stats() -> dict:
    query = f"""
    PREFIX wd: <{ENTITY_PREFIX}>
    PREFIX wdt: <{PROP_PREFIX}>
    SELECT ?an_project (COUNT(?item) AS ?count) WHERE {{
      ?item wdt:P1 wd:{CLASS_DIGITAL_OBJECT} .
      OPTIONAL {{ ?item wdt:P12 ?an_project . }}
    }}
    GROUP BY ?an_project
    """
    rows = await _run_query(query)
    by_project = {}
    total = 0
    for r in rows:
        proj = _binding_value(r, "an_project") or "(χωρίς AN Project)"
        count = int(_binding_value(r, "count") or 0)
        by_project[proj] = count
        total += count

    coll_query = f"""
    PREFIX wd: <{ENTITY_PREFIX}>
    PREFIX wdt: <{PROP_PREFIX}>
    SELECT (COUNT(?coll) AS ?count) WHERE {{
      ?coll wdt:P1 wd:{CLASS_COLLECTION} .
    }}
    """
    coll_rows = await _run_query(coll_query)
    total_collections = int(_binding_value(coll_rows[0], "count") or 0) if coll_rows else 0

    return {
        "total_items": total,
        "total_collections": total_collections,
        "items_by_an_project": by_project,
    }
