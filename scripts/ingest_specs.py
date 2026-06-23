#!/usr/bin/env python3
"""Host-aware bulk ingest of WB OpenAPI specs into endpoints.yaml.

Unlike sync_swagger (one --host per run), this resolves the host per operation
(operation > path > root servers), drops *-sandbox* hosts, infers a scope from
the host, and infers safety from the verb with a read-POST heuristic so report/
list endpoints stay usable by read-only tools. Additive + idempotent.

Usage: python scripts/ingest_specs.py --specs /tmp/specs --catalog wb_mcp/endpoints.yaml [--apply]
"""
from __future__ import annotations
import argparse, glob, os, re, yaml

HOST_SCOPE = {
    "content-api":"content","discounts-prices-api":"prices","marketplace-api":"marketplace",
    "supplies-api":"supplies","advert-api":"promotion","advert-media-api":"promotion",
    "dp-calendar-api":"promotion","feedbacks-api":"feedbacks","buyer-chat-api":"chat",
    "returns-api":"returns","seller-analytics-api":"analytics","statistics-api":"statistics",
    "common-api":"common","finance-api":"finance","documents-api":"documents",
    "devapi-digital":"documents","user-management-api":"general",
}
READ_POST = re.compile(r"\b(get|list|all|info|details?|reports?|history|search|filter|count|remains|balance|coefficients?|rating|feedbacks|questions|goods|warehouses|stats|tariffs|status)\b", re.I)
MUTATE = re.compile(r"\b(cancel|confirm|reject|deliver|receive|prepare|create|delete|remove|upload|refund|reshipment|assemble|pack|ship|add|set|update|edit|close|save)\b", re.I)

def host_of(op, ops, root):
    for src in (op.get("servers"), ops.get("servers"), root):
        if src:
            for s in src:
                u=(s.get("url") or "")
                h=u.replace("https://","").replace("http://","").split("/")[0]
                if h and "sandbox" not in h:
                    return h
    return ""

def scope_of(host):
    key=host.split(".")[0]
    return HOST_SCOPE.get(key, key)

def slug(service, method, path):
    s=re.sub(r"[^a-z0-9]+","_",path.lower()).strip("_")
    s=re.sub(r"_v\d+_","_",s)
    return f"{service}_{method.lower()}_{s}"[:60]

def safety_of(method, path, oid):
    m=method.lower()
    if m in ("get","head"): return "read"
    if m=="delete": return "destructive"
    # Only POST may be a read-with-body (search/list/report). PUT and PATCH are
    # always mutations — the READ_POST allow-list must NOT downgrade them, or a
    # mutating endpoint slips past the safety gate in call_method.
    if m=="post":
        if MUTATE.search(path+" "+oid): return "write"
        return "read" if READ_POST.search(path+" "+oid) else "write"
    if m in ("put","patch"): return "write"
    return "write"

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--specs",required=True); ap.add_argument("--catalog",required=True)
    ap.add_argument("--service",default="wb"); ap.add_argument("--apply",action="store_true")
    a=ap.parse_args()
    cat=yaml.safe_load(open(a.catalog,encoding="utf-8")) or {}
    eps=cat.setdefault("endpoints",[])
    seen_oid={e["operation_id"] for e in eps}
    seen_path={(e["method"].upper(),e["host"],e["path"]) for e in eps}
    added=[]; by_scope={}; by_safety={}
    for fn in sorted(glob.glob(os.path.join(a.specs,"*.yaml"))):
        spec=yaml.safe_load(open(fn,encoding="utf-8")); root=spec.get("servers")
        for path,ops in (spec.get("paths") or {}).items():
            for method,op in ops.items():
                if method.lower() not in ("get","post","put","patch","delete"): continue
                if not isinstance(op,dict): continue
                host=host_of(op,ops,root)
                if not host: continue
                if (method.upper(),host,path) in seen_path: continue
                oid=slug(a.service,method,path); base=oid; i=2
                while oid in seen_oid: oid=f"{base}_{i}"; i+=1
                seen_oid.add(oid); seen_path.add((method.upper(),host,path))
                sc=scope_of(host); sf=safety_of(method,path,oid)
                tags=op.get("tags") or []
                rec={"operation_id":oid,"section":(tags[0] if tags else sc),"method":method.upper(),
                     "host":host,"path":path,"scope":sc,"safety":sf,
                     "summary":(op.get("summary") or op.get("description") or "").strip()[:180],
                     "doc":""}
                eps.append(rec); added.append(rec)
                by_scope[sc]=by_scope.get(sc,0)+1
                by_safety[sf]=by_safety.get(sf,0)+1
    print(f"новых: {len(added)} | каталог теперь: {len(eps)}")
    print("по scope:", dict(sorted(by_scope.items())))
    print("по safety:", dict(sorted(by_safety.items())))
    if a.apply:
        yaml.safe_dump(cat,open(a.catalog,"w",encoding="utf-8"),allow_unicode=True,sort_keys=False)
        print("ЗАПИСАНО ->",a.catalog)
    else:
        print("(dry-run; --apply чтобы записать)")

if __name__=="__main__": main()
