"""
oai.py — minimal OAI-PMH 2.0 provider for the Archipelago Wikibase.

Lets Repox (or any OAI-PMH harvester) pull the metadata automatically:

    <api>/oai?verb=Identify
    <api>/oai?verb=ListSets
    <api>/oai?verb=ListRecords&metadataPrefix=oai_dc
    <api>/oai?verb=ListRecords&metadataPrefix=oai_dc&from=2026-10-01   <- incremental update
    <api>/oai?verb=GetRecord&identifier=oai:archipelago:Q486&metadataPrefix=edm

Sets = collections (setSpec = collection Q-ID). Datestamps come from the
Wikibase `schema:dateModified` (fallback: time of the last cache refresh).

Env vars: OAI_SOURCE=live|dump (default live), OAI_DUMP=<path to .ttl>,
OAI_PAGE_SIZE (default 100), OAI_CACHE_SECONDS (default 600).
Deleted items are not reported (the Wikibase has none: duplicates are only de-typed).
"""
import base64
import json
import os
import time
from datetime import datetime, timezone
from xml.sax.saxutils import escape

from fastapi import APIRouter, Request
from fastapi.responses import Response

import repox_records as rr

router = APIRouter()
PAGE = int(os.getenv("OAI_PAGE_SIZE", "100"))
TTL = int(os.getenv("OAI_CACHE_SECONDS", "600"))
PREFIX = "oai:archipelago:"
_cache = {"t": 0, "records": []}

FORMATS = {
    "oai_dc": ("http://www.openarchives.org/OAI/2.0/oai_dc.xsd",
               "http://www.openarchives.org/OAI/2.0/oai_dc/"),
    "edm": ("http://www.europeana.eu/schemas/edm/EDM.xsd",
            "http://www.europeana.eu/schemas/edm/"),
}
ERRORS_NO_ECHO = {"badVerb", "badArgument"}


def records():
    if time.time() - _cache["t"] > TTL or not _cache["records"]:
        _cache["records"] = rr.load_records(os.getenv("OAI_SOURCE", "live"), os.getenv("OAI_DUMP"))
        _cache["t"] = time.time()
    return _cache["records"]


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def envelope(request_attrs, body):
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
            'xsi:schemaLocation="http://www.openarchives.org/OAI/2.0/ '
            'http://www.openarchives.org/OAI/2.0/OAI-PMH.xsd">'
            f"<responseDate>{now()}</responseDate>{request_attrs}{body}</OAI-PMH>")


def error(code, msg, req):
    return envelope(req, f'<error code="{code}">{escape(msg)}</error>')


def header(r):
    return (f"<header><identifier>{PREFIX}{r['qid']}</identifier>"
            f"<datestamp>{r['datestamp']}</datestamp><setSpec>{r['set']}</setSpec></header>")


def record_xml(r, prefix):
    return f"<record>{header(r)}<metadata>{rr.SERIALISERS[prefix](r)}</metadata></record>"


def parse_date(v):
    for fmt, n in (("%Y-%m-%dT%H:%M:%SZ", 20), ("%Y-%m-%d", 10)):
        try:
            return datetime.strptime(v, fmt).strftime("%Y-%m-%dT%H:%M:%SZ") if n == 20 else \
                datetime.strptime(v, fmt).strftime("%Y-%m-%dT00:00:00Z")
        except ValueError:
            pass
    return None


@router.get("/oai", tags=["oai-pmh"], summary="OAI-PMH 2.0 endpoint (for Repox harvesting)")
def oai(request: Request):
    q = dict(request.query_params)
    base = str(request.url).split("?")[0]
    verb = q.get("verb")
    req_attrs = lambda keep=True: (
        "<request" + (" " + " ".join(f'{k}="{escape(v)}"' for k, v in q.items()) if keep else "")
        + f">{base}</request>")
    xml = lambda s: Response(s, media_type="text/xml; charset=utf-8")

    if verb not in {"Identify", "ListMetadataFormats", "ListSets", "ListIdentifiers",
                    "ListRecords", "GetRecord"}:
        return xml(error("badVerb", "Illegal or missing verb", req_attrs(False)))
    allowed = {"Identify": set(), "ListMetadataFormats": {"identifier"}, "ListSets": {"resumptionToken"},
               "ListIdentifiers": {"metadataPrefix", "from", "until", "set", "resumptionToken"},
               "ListRecords": {"metadataPrefix", "from", "until", "set", "resumptionToken"},
               "GetRecord": {"identifier", "metadataPrefix"}}[verb]
    extra = set(q) - allowed - {"verb"}
    if extra:
        return xml(error("badArgument", f"Illegal argument(s): {', '.join(sorted(extra))}",
                         req_attrs(False)))
    req = req_attrs()

    try:
        recs = records()
    except Exception as e:  # SPARQL unreachable
        return xml(error("badArgument", f"Upstream SPARQL error: {e}", req))

    if verb == "Identify":
        earliest = min((r["datestamp"] for r in recs), default=now())
        return xml(envelope(req, (
            "<Identify><repositoryName>Archipelago Knowledge Base (Digital Cyclades)</repositoryName>"
            f"<baseURL>{base}</baseURL><protocolVersion>2.0</protocolVersion>"
            "<adminEmail>info@archipelagonetwork.org</adminEmail>"
            f"<earliestDatestamp>{earliest}</earliestDatestamp>"
            "<deletedRecord>no</deletedRecord><granularity>YYYY-MM-DDThh:mm:ssZ</granularity>"
            "</Identify>")))

    if verb == "ListMetadataFormats":
        return xml(envelope(req, "<ListMetadataFormats>" + "".join(
            f"<metadataFormat><metadataPrefix>{p}</metadataPrefix><schema>{s}</schema>"
            f"<metadataNamespace>{n}</metadataNamespace></metadataFormat>"
            for p, (s, n) in FORMATS.items()) + "</ListMetadataFormats>"))

    if verb == "ListSets":
        return xml(envelope(req, "<ListSets>" + "".join(
            f"<set><setSpec>{k}</setSpec><setName>{escape(v)}</setName></set>"
            for k, v in rr.sets_of(recs).items()) + "</ListSets>"))

    if verb == "GetRecord":
        if "identifier" not in q or "metadataPrefix" not in q:
            return xml(error("badArgument", "identifier and metadataPrefix required", req))
        if q["metadataPrefix"] not in FORMATS:
            return xml(error("cannotDisseminateFormat", "Unsupported metadataPrefix", req))
        qid = q["identifier"].replace(PREFIX, "")
        r = next((x for x in recs if x["qid"] == qid), None)
        if not r:
            return xml(error("idDoesNotExist", "No such record", req))
        return xml(envelope(req, f"<GetRecord>{record_xml(r, q['metadataPrefix'])}</GetRecord>"))

    # ListIdentifiers / ListRecords (with resumption tokens)
    state = {}
    if "resumptionToken" in q:
        try:
            state = json.loads(base64.urlsafe_b64decode(q["resumptionToken"]).decode())
        except Exception:
            return xml(error("badResumptionToken", "Invalid token", req))
    else:
        if "metadataPrefix" not in q:
            return xml(error("badArgument", "metadataPrefix required", req))
        state = {"p": q["metadataPrefix"], "from": q.get("from"), "until": q.get("until"),
                 "set": q.get("set"), "o": 0}
    if state["p"] not in FORMATS:
        return xml(error("cannotDisseminateFormat", "Unsupported metadataPrefix", req))
    f = parse_date(state["from"]) if state.get("from") else None
    u = parse_date(state["until"]) if state.get("until") else None
    if (state.get("from") and not f) or (state.get("until") and not u):
        return xml(error("badArgument", "Bad date (use YYYY-MM-DD or YYYY-MM-DDThh:mm:ssZ)", req))
    if u and state.get("until") and len(state["until"]) == 10:
        u = u.replace("T00:00:00Z", "T23:59:59Z")
    sel = [r for r in recs if (not f or r["datestamp"] >= f) and (not u or r["datestamp"] <= u)
           and (not state.get("set") or r["set"] == state["set"])]
    if not sel:
        return xml(error("noRecordsMatch", "No records match the request", req))
    o = state["o"]
    chunk = sel[o:o + PAGE]
    token = ""
    if o + PAGE < len(sel):
        nxt = dict(state, o=o + PAGE)
        t = base64.urlsafe_b64encode(json.dumps(nxt).encode()).decode()
        token = f'<resumptionToken completeListSize="{len(sel)}" cursor="{o}">{t}</resumptionToken>'
    elif "resumptionToken" in q:
        token = f'<resumptionToken completeListSize="{len(sel)}" cursor="{o}"/>'
    if verb == "ListIdentifiers":
        body = "<ListIdentifiers>" + "".join(header(r) for r in chunk) + token + "</ListIdentifiers>"
    else:
        body = "<ListRecords>" + "".join(record_xml(r, state["p"]) for r in chunk) + token + "</ListRecords>"
    return xml(envelope(req, body))
