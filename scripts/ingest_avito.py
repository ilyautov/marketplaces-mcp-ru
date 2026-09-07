#!/usr/bin/env python3
"""Build avito_mcp/endpoints.yaml.

Avito publishes one OpenAPI document per section behind its developer portal
(www.avito.ru/web/1/openapi/info/<slug>, browser-only — curl gets a 429 captcha
wall). The seller-relevant sections were captured by hand into compact
operation lists (scripts/avito_specs/ops_*.json); the autoload section is the
full OpenAPI document and goes through the generic ingest helpers.

    python3 scripts/ingest_avito.py --apply

Compact record fields: id (operationId), m (method), path, sum (RU summary),
q (query params), body (comma-separated body fields), ip (items_path),
pag (pagination style), safety (override), dep (deprecated flag).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ingest_openapi import READ_VERBS, items_path_of, safety, snake  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SPECS = ROOT / "scripts" / "avito_specs"
OUT = ROOT / "avito_mcp" / "endpoints.yaml"
HOST = "api.avito.ru"
PREFIX = "avito"


def keywords(op_id: str) -> list[str]:
    return [w for w in snake(op_id).split("_") if len(w) > 2 and w not in READ_VERBS]


def from_compact(section: str, doc: str, op: dict) -> dict:
    rec = {
        "operation_id": f"{PREFIX}_{snake(op['id'])}",
        "section": section,
        "method": op["m"],
        "host": HOST,
        "path": op["path"],
        "scope": "seller",
        "safety": op.get("safety") or safety(op["m"], op["id"], op["path"]),
        "pagination": op.get("pag", "none"),
        "summary": ("[устарело] " if op.get("dep") else "") + op["sum"],
        "doc": f"{doc}#operation/{op['id']}",
    }
    if op.get("ip"):
        rec["items_path"] = op["ip"]
    params = {}
    if op.get("q"):
        params["query"] = ", ".join(op["q"])
    if op.get("body"):
        params["body"] = op["body"]
    if params:
        rec["params"] = params
    kw = keywords(op["id"])
    if kw:
        rec["keywords"] = kw
    return rec


def from_openapi(section: str, doc: str, spec: dict) -> list[dict]:
    out = []
    for path, item in spec["paths"].items():
        shared = item.get("parameters", [])
        for m, op in item.items():
            if m not in ("get", "post", "put", "patch", "delete"):
                continue
            summary = (op.get("summary") or "").strip()
            if "(deprecated)" in summary or op.get("deprecated"):
                continue  # Avito keeps old report endpoints around; skip them
            params = shared + op.get("parameters", [])
            q = [p["name"] for p in params if isinstance(p, dict) and p.get("in") == "query"]
            oid = op.get("operationId") or snake(m + "_" + path)
            rec = {
                "operation_id": f"{PREFIX}_{snake(oid)}",
                "section": section,
                "method": m.upper(),
                "host": HOST,
                "path": path,
                "scope": "seller",
                "safety": safety(m, oid, path),
                "pagination": "page_query" if "page" in q else "none",
                "summary": summary[:180],
                "doc": f"{doc}#operation/{oid}",
            }
            ip = items_path_of(spec, op)
            if ip:
                rec["items_path"] = ip
            p = {}
            if q:
                p["query"] = ", ".join(q)
            rb = op.get("requestBody")
            if isinstance(rb, dict):
                schema = (rb.get("content") or {}).get("application/json", {}).get("schema", {})
                props = list((schema.get("properties") or {}).keys()) if isinstance(schema, dict) else []
                if props:
                    p["body"] = ",".join(props[:12])
                elif schema:
                    p["body"] = "object"
            if p:
                rec["params"] = p
            kw = keywords(oid)
            if kw:
                rec["keywords"] = kw
            out.append(rec)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    eps: list[dict] = []
    for f in sorted(SPECS.glob("ops_*.json")):
        for slug, sec in json.loads(f.read_text(encoding="utf-8")).items():
            for op in sec["ops"]:
                eps.append(from_compact(sec["section"], sec["doc"], op))
    autoload = json.loads((SPECS / "autoload.openapi.json").read_text(encoding="utf-8"))
    eps += from_openapi("Автозагрузка (выгрузка объявлений файлом)",
                        "https://developers.avito.ru/api-catalog/autoload/documentation", autoload)
    seen = set()
    for e in eps:
        assert e["operation_id"] not in seen, e["operation_id"]
        seen.add(e["operation_id"])
    cat = {"default_host": HOST, "endpoints": eps}
    from collections import Counter
    print(f"endpoints: {len(eps)}", dict(Counter(e['safety'] for e in eps)))
    print(dict(Counter(e["section"] for e in eps)))
    if a.apply:
        OUT.write_text(yaml.safe_dump(cat, allow_unicode=True, sort_keys=False), encoding="utf-8")
        print("WRITTEN", OUT)


if __name__ == "__main__":
    main()
