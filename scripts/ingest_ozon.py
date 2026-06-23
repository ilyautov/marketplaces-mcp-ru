#!/usr/bin/env python3
"""Ingest Ozon Seller swagger into ozon_mcp/endpoints.yaml (host-aware not needed:
single host). Ozon is ~all POST, so safety is path/operationId-driven with a
read/mutate heuristic, then corrected by PCDCK curated safety_overrides
(keyed by swagger operationId). Deprecated methods skipped. Additive+idempotent.
"""
from __future__ import annotations
import argparse, json, re, yaml
from pathlib import Path

HOST="api-seller.ozon.ru"
READ=re.compile(r"(list|info|get|report|analytics|financ|rating|history|search|/stocks\b|/stock\b|description|timeslot|available|status|tree|attribute|certificate|/info/)",re.I)
MUTATE=re.compile(r"(import|update|create|delete|/set|/add|ship|cancel|activate|deactivat|archive|move|send|confirm|reject|refund|/change|assign|generate|exemplar/set|unpublish|publish|upload|/act/|/draft/|register)",re.I)

def safety(path,oid):
    t=path+" "+(oid or "")
    if MUTATE.search(t): return "destructive" if re.search(r"delete",t,re.I) else "write"
    if READ.search(t): return "read"
    return "write"

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--spec",required=True); ap.add_argument("--catalog",required=True)
    ap.add_argument("--overrides",default=""); ap.add_argument("--deprecated",default="")
    ap.add_argument("--apply",action="store_true")
    a=ap.parse_args()
    spec=json.load(open(a.spec,encoding="utf-8"))
    cat=yaml.safe_load(open(a.catalog,encoding="utf-8")) or {}
    eps=cat.setdefault("endpoints",[])
    seen_oid={e["operation_id"] for e in eps}
    seen_path={(e["method"].upper(),e["path"]) for e in eps}
    ov={}; dep=set()
    if a.overrides:
        for r in (yaml.safe_load(open(a.overrides)) or []):
            if isinstance(r,dict) and r.get("operation_id"): ov[r["operation_id"]]=r.get("safety")
    if a.deprecated:
        dd=yaml.safe_load(open(a.deprecated)) or []
        for r in dd:
            dep.add(r if isinstance(r,str) else (r.get("operation_id") or r.get("path")))
    added=[]; skipped_dep=0; from collections import Counter; bys=Counter()
    for path,ops in (spec.get("paths") or {}).items():
        for method,op in ops.items():
            if method.lower() not in ("get","post","put","patch","delete"): continue
            if not isinstance(op,dict): continue
            swid=op.get("operationId")
            if swid in dep or path in dep: skipped_dep+=1; continue
            if (method.upper(),path) in seen_path: continue
            slug=re.sub(r"[^a-z0-9]+","_",path.lower()).strip("_"); slug=re.sub(r"_v\d+_","_",slug)
            oid=f"ozon_{method.lower()}_{slug}"[:60]; base=oid; i=2
            while oid in seen_oid: oid=f"{base}_{i}"; i+=1
            seen_oid.add(oid); seen_path.add((method.upper(),path))
            sf = ov.get(swid) or safety(path,swid)
            tags=op.get("tags") or []
            rec={"operation_id":oid,"section":(tags[0] if tags else "imported"),"method":method.upper(),
                 "host":HOST,"path":path,"scope":"seller","safety":sf,
                 "summary":(op.get("summary") or op.get("description") or "").strip()[:180],"doc":""}
            eps.append(rec); added.append(rec); bys[sf]+=1
    print(f"новых: {len(added)} | пропущено deprecated: {skipped_dep} | каталог: {len(eps)}")
    print("safety новых:", dict(bys), "| overrides применено где совпало operationId")
    if a.apply:
        yaml.safe_dump(cat,open(a.catalog,"w",encoding="utf-8"),allow_unicode=True,sort_keys=False)
        print("ЗАПИСАНО")
    else: print("(dry-run)")

if __name__=="__main__": main()
