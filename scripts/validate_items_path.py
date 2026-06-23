#!/usr/bin/env python3
"""Live-validate items_path against real responses and auto-fix unambiguous
misses (spec != live). Calls read endpoints with a generic body/query; where the
declared items_path does not dig to a list but the response contains exactly one
array (depth<=3), rewrites items_path to the real location.

Throttled; skips endpoints needing unknown params (non-200) and a host blocklist.
"""
from __future__ import annotations
import asyncio, os, sys, yaml
from pathlib import Path
sys.path.insert(0,'.')
from core.registry import Catalog
from core.client import MarketplaceClient, ServiceConfig

GENERIC = {"limit":10,"last_id":"","filter":{},"dir":"ASC","visibility":"ALL"}

def dig(o,dotted):
    cur=o
    for p in (dotted or "").split("."):
        if isinstance(cur,dict): cur=cur.get(p)
        else: return None
    return cur

def find_arrays(o,prefix="",depth=0,out=None):
    if out is None: out=[]
    if depth>3 or not isinstance(o,dict): return out
    for k,v in o.items():
        if isinstance(v,list): out.append((prefix+k,len(v)))
        elif isinstance(v,dict): find_arrays(v,prefix+k+".",depth+1,out)
    return out

async def validate(svc, cfg, catalog_path, skip_hosts, cap, delay):
    c=Catalog.from_yaml(Path(catalog_path)); client=MarketplaceClient(cfg)
    cat=yaml.safe_load(Path(catalog_path).read_text())
    rec_by_key={(e['method'].upper(),e['path']):e for e in cat['endpoints']}
    reads=[e for e in c.all() if e.safety=='read' and e.items_path and e.host not in skip_hosts]
    ok=miss=fixed=skip=0; n=0
    for e in reads:
        if n>=cap: break
        body = dict(GENERIC) if e.method=='POST' else None
        query = dict(GENERIC) if e.method=='GET' else None
        try:
            r=await asyncio.wait_for(client.call_spec(e, json_body=body, query=query), timeout=6)
        except Exception: skip+=1; continue
        if not r.get('ok'): skip+=1; await asyncio.sleep(delay); continue
        n+=1
        print('.',end='',flush=True)
        data=r.get('data')
        dug=dig(data,e.items_path) if isinstance(data,dict) else (data if isinstance(data,list) else None)
        if isinstance(dug,list): ok+=1
        else:
            arrs=find_arrays(data) if isinstance(data,dict) else []
            if len(arrs)==1:
                real=arrs[0][0]; rec_by_key[(e.method,e.path)]['items_path']=real; fixed+=1
                print(f"  FIX {e.path}: {e.items_path} -> {real}")
            else:
                miss+=1; print(f"  ?? {e.path}: ip={e.items_path} arrays={[a[0] for a in arrs][:4]}")
        await asyncio.sleep(delay)
    Path(catalog_path).write_text(yaml.safe_dump(cat,allow_unicode=True,sort_keys=False))
    print(f"[{svc}] проверено(200)={n} ok={ok} авто-фикс={fixed} неоднозначно={miss} пропущено(non200)={skip}")

async def main():
    which=sys.argv[1] if len(sys.argv)>1 else 'ozon'
    if which=='ozon':
        cfg=ServiceConfig(name="ozon",scheme="https",fields=["client_id","api_key"],
          env_map={"client_id":"OZON_CLIENT_ID","api_key":"OZON_API_KEY"},
          build_headers=lambda c:{"Client-Id":c.get("client_id",""),"Api-Key":c.get("api_key",""),"Content-Type":"application/json"})
        await validate("ozon",cfg,"ozon_mcp/endpoints.yaml",set(),cap=400,delay=0.4)
    else:
        cfg=ServiceConfig(name="wb",scheme="https",fields=["token"],
          env_map={"token":"WB_API_TOKEN"},build_headers=lambda c:{"Authorization":c.get("token","")})
        await validate("wb",cfg,"wb_mcp/endpoints.yaml",{"statistics-api.wildberries.ru"},cap=400,delay=1.0)

asyncio.run(main())
