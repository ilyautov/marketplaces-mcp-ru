#!/usr/bin/env python3
"""Enrich an endpoints.yaml catalog from an official OpenAPI/Swagger spec.

Run this LOCALLY (on a RU IP — WB/Ozon hosts block many foreign IPs). It reads
a swagger JSON/YAML, extracts operations, and appends any endpoints missing
from the curated catalog so coverage grows toward "every method" without
hand-writing each record.

Usage:
    python scripts/sync_swagger.py --spec wb_content.json \
        --catalog wb_mcp/endpoints.yaml --service wb --section content \
        --host content-api.wildberries.ru

Notes:
- This is additive and idempotent: existing operation_ids are never overwritten,
  so your curated safety levels and summaries are preserved.
- Safety is inferred from the HTTP verb; review and tighten by hand afterwards.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import yaml

_VERB_SAFETY = {"get": "read", "head": "read", "post": "write",
                "put": "write", "patch": "write", "delete": "destructive"}


def _load_spec(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if path.suffix in (".yaml", ".yml"):
        return yaml.safe_load(text)
    return json.loads(text)


def _op_id(service: str, method: str, path: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", path.lower()).strip("_")
    slug = re.sub(r"_v\d+_", "_", slug)
    return f"{service}_{method.lower()}_{slug}"[:60]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True, type=Path)
    ap.add_argument("--catalog", required=True, type=Path)
    ap.add_argument("--service", required=True)
    ap.add_argument("--section", default="imported")
    ap.add_argument("--host", default="")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    spec = _load_spec(args.spec)
    catalog = yaml.safe_load(args.catalog.read_text(encoding="utf-8")) or {}
    existing = {e["operation_id"] for e in catalog.get("endpoints", [])}
    existing_paths = {(e["method"].upper(), e["path"]) for e in catalog.get("endpoints", [])}
    host = args.host or catalog.get("default_host", "")

    added = []
    for path, item in (spec.get("paths") or {}).items():
        for method, op in item.items():
            if method.lower() not in _VERB_SAFETY:
                continue
            if (method.upper(), path) in existing_paths:
                continue
            oid = _op_id(args.service, method, path)
            base = oid
            i = 2
            while oid in existing:
                oid = f"{base}_{i}"
                i += 1
            existing.add(oid)
            added.append({
                "operation_id": oid,
                "section": op.get("tags", [args.section])[0] if op.get("tags") else args.section,
                "method": method.upper(),
                "host": host,
                "path": path,
                "scope": args.service,
                "safety": _VERB_SAFETY[method.lower()],
                "summary": (op.get("summary") or op.get("description") or "").strip()[:200],
                "doc": "",
            })

    print(f"Found {len(added)} new endpoints (catalog had {len(catalog.get('endpoints', []))}).")
    if args.dry_run or not added:
        for a in added[:20]:
            print(f"  + {a['operation_id']:50} {a['method']:6} {a['path']}")
        return

    catalog.setdefault("endpoints", []).extend(added)
    args.catalog.write_text(
        yaml.safe_dump(catalog, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    print(f"Appended {len(added)} endpoints to {args.catalog}.")


if __name__ == "__main__":
    main()
