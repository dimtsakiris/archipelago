#!/usr/bin/env python3
"""
wikibase_to_repox.py — export Archipelago Wikibase items as XML for Repox.

MANUAL / SCHEDULED route (no server needed): writes a folder of XML files that
Repox can ingest as a folder / HTTP / FTP data source (check which your Repox
instance offers), plus one combined file and a zip.

    # everything, Dublin Core, from the live Wikibase
    python scripts/wikibase_to_repox.py --out-dir repox_export

    # only items changed since a date (incremental)
    python scripts/wikibase_to_repox.py --since 2026-10-01 --out-dir repox_update

    # remember the last run automatically (state file inside out-dir)
    python scripts/wikibase_to_repox.py --incremental --out-dir repox_export

    # EDM instead of Dublin Core; offline test against the RDF dump
    python scripts/wikibase_to_repox.py --format edm --source dump \
        --dump rdf_dataset/archipelago_full.ttl --out-dir /tmp/test

For the AUTOMATED route use the OAI-PMH endpoint of the API (archipelago-api/oai.py).
"""
import argparse
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "archipelago-api"))
import repox_records as rr  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["live", "dump"], default="live")
    ap.add_argument("--dump", help="RDF file when --source dump")
    ap.add_argument("--format", choices=list(rr.SERIALISERS), default="oai_dc")
    ap.add_argument("--since", help="YYYY-MM-DD: only items modified on/after this date")
    ap.add_argument("--incremental", action="store_true",
                    help="use/update out-dir/state.json (last successful run)")
    ap.add_argument("--out-dir", default="repox_export")
    ap.add_argument("--zip", action="store_true", help="also write records.zip")
    a = ap.parse_args()

    out = Path(a.out_dir); out.mkdir(parents=True, exist_ok=True)
    state_f = out / "state.json"
    since = a.since
    if a.incremental and not since and state_f.exists():
        since = json.loads(state_f.read_text())["last_run"]

    started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    recs = rr.load_records(a.source, a.dump)
    total = len(recs)
    if since:
        s = since if len(since) > 10 else since + "T00:00:00Z"
        recs = [r for r in recs if r["datestamp"] >= s]

    ser = rr.SERIALISERS[a.format]
    rec_dir = out / "records"; rec_dir.mkdir(exist_ok=True)
    combined = ['<?xml version="1.0" encoding="UTF-8"?>', "<records>"]
    for r in recs:
        xml = ser(r)
        (rec_dir / f"{r['qid']}.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>' + xml,
                                                  encoding="utf-8")
        combined.append(f'<record id="{r["qid"]}" set="{r["set"]}" datestamp="{r["datestamp"]}">{xml}</record>')
    combined.append("</records>")
    (out / "records.xml").write_text("\n".join(combined), encoding="utf-8")
    if a.zip:
        with zipfile.ZipFile(out / "records.zip", "w", zipfile.ZIP_DEFLATED) as z:
            for f in sorted(rec_dir.glob("*.xml")):
                z.write(f, f.name)
    if a.incremental:
        state_f.write_text(json.dumps({"last_run": started, "format": a.format}))
    print(f"{len(recs)} of {total} records exported ({a.format}"
          f"{', since ' + since if since else ''}) -> {out}")


if __name__ == "__main__":
    main()
