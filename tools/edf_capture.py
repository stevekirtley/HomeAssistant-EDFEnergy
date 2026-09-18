"""mitmproxy addon: record every EDF / Kraken request and response as JSONL.

Usage:
    mitmdump -s _docs/tools/edf_capture.py -s _docs/tools/hostlog.py \
        -w _docs/tools/snapshots/edf_flows.mitm

Each matching flow is appended to _docs/tools/snapshots/edf_capture.jsonl as it
completes, and a one-line summary is printed to the console. Authorization
headers are redacted in the console line only; the JSONL keeps them because the
snapshots folder is gitignored and the raw token shape matters for replay.
"""
import json
import os
from datetime import datetime

from mitmproxy import http

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "snapshots")
OUT_FILE = os.path.join(OUT_DIR, "edf_capture.jsonl")

INTERESTING = (
    "edfenergy.com",
    "edfgb-kraken.energy",
    "edf.",  # any edf.* subdomain
    "kraken",
    "octopus",
)


def _wanted(host: str) -> bool:
    host = (host or "").lower()
    return any(marker in host for marker in INTERESTING)


def _body(msg) -> str | None:
    if not msg.content:
        return None
    try:
        return msg.get_text(strict=False)
    except Exception:
        return f"<{len(msg.content)} bytes binary>"


def response(flow: http.HTTPFlow) -> None:
    if not _wanted(flow.request.pretty_host):
        return
    os.makedirs(OUT_DIR, exist_ok=True)
    record = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "method": flow.request.method,
        "url": flow.request.pretty_url,
        "request_headers": dict(flow.request.headers),
        "request_body": _body(flow.request),
        "status": flow.response.status_code if flow.response else None,
        "response_headers": dict(flow.response.headers) if flow.response else None,
        "response_body": _body(flow.response) if flow.response else None,
    }
    with open(OUT_FILE, "a") as fh:
        fh.write(json.dumps(record) + "\n")

    auth = flow.request.headers.get("Authorization", "")
    auth_note = f" auth={auth[:12]}…" if auth else ""
    body = record["response_body"] or ""
    print(
        f"[EDF] {record['status']} {record['method']} {record['url']}{auth_note}"
        f" -> {body[:160].replace(chr(10), ' ')}"
    )
