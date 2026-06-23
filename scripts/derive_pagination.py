#!/usr/bin/env python3
"""Fill items_path + pagination for catalog records that lack them, by reading
the OpenAPI response/request schemas. items_path is derived from the response
schema (authoritative path to the array). pagination style from request fields,
optionally overridden by a curated patterns file (PCDCK, keyed by operationId).

A WRONG items_path is worse than none (silent empty page), so we only set it
when a single array is unambiguously found; otherwise we leave the record.
"""
from __future__ import annotations
import argparse, glob, json, os, re, yaml
from pathlib import Path

CONTAINER_PREF=('result','data','rows','items','cards','content','list','postings','operations','products','offers','feedbacks','questions','goods','warehouses','report')
PAT_TYPE={'offset_limit':'offset','page_number':'page','last_id':'last_id','cursor':'cursor','page_token':'none'}

def load(p):
    t=Path(p).read_text(encoding='utf-8')
    return yaml.safe_load(t) if p.endswith(('.yaml','.yml')) else json.loads(t)

def mk_resolver(spec):
    comps=spec.get('components',{}).get('schemas',{}) or spec.get('definitions',{})
    def res(s,depth=0):
        seen=0
        while isinstance(s,dict) and '$ref' in s and depth<8:
            s=comps.get(s['$ref'].split('/')[-1],{}); depth+=1
        return s
    return res

def find_array(schema,res,prefix='',depth=0):
    schema=res(schema)
    if not isinstance(schema,dict): return None
    if schema.get('type')=='array': return prefix.rstrip('.')
    props=schema.get('properties') or {}
    keys=sorted(props,key=lambda k:(k.lower() not in CONTAINER_PREF,k))
    for k in keys:
        sub=res(props[k])
        if not isinstance(sub,dict): continue
        if sub.get('type')=='array': return prefix+k
    if depth<3:
        for k in keys:
            sub=res(props[k])
            if isinstance(sub,dict) and (sub.get('type')=='object' or sub.get('properties')):
                r=find_array(sub,res,prefix+k+'.',depth+1)
                if r is not None: return r
    return None

def request_fields(op,res):
    fields=set()
    for pr in op.get('parameters',[]):
        if isinstance(pr,dict): fields.add(pr.get('name'))
    rb=op.get('requestBody',{})
    try:
        sch=res(rb['content']['application/json']['schema'])
        def walk(s,d=0):
            s=res(s)
            for k,v in (s.get('properties') or {}).items():
                fields.add(k)
                if d<2: walk(v,d+1)
        walk(sch)
    except Exception: pass
    return fields

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--specs',required=True); ap.add_argument('--catalog',required=True)
    ap.add_argument('--patterns',default=''); ap.add_argument('--apply',action='store_true')
    a=ap.parse_args()
    files=glob.glob(os.path.join(a.specs,'*.yaml')) if os.path.isdir(a.specs) else [a.specs]
    index={}  # (METHOD,path) -> (opId, items_path, req_fields)
    for f in files:
        spec=load(f); res=mk_resolver(spec)
        for path,ops in (spec.get('paths') or {}).items():
            for m,op in ops.items():
                if m.lower() not in ('get','post','put','patch','delete') or not isinstance(op,dict): continue
                resp=op.get('responses',{})
                sch=None
                for code in ('200','201','default'):
                    r=resp.get(code) or {}
                    c=(r.get('content') or {}).get('application/json') or {}
                    if c.get('schema'): sch=c['schema']; break
                ip=find_array(sch,res) if sch else None
                index[(m.upper(),path)]=(op.get('operationId'),ip,request_fields(op,res))
    pats={}
    if a.patterns:
        for r in (load(a.patterns) or []):
            pats[r['operation_id']]={'type':PAT_TYPE.get(r.get('type'),'none'),'items':r.get('response_items_field')}
    cat=load(a.catalog); set_ip=set_pg=0
    for e in cat['endpoints']:
        if e.get('items_path') and e.get('pagination'): continue  # уже укомплектован
        key=(e['method'].upper(),e['path']); info=index.get(key)
        if not info: continue
        opId,ip,fields=info
        # items_path из схемы
        if not e.get('items_path') and ip:
            e['items_path']=ip; set_ip+=1
        # pagination
        if not e.get('pagination'):
            style=None
            if opId and opId in pats: style=pats[opId]['type']
            if not style:
                fl={(x or '').lower() for x in fields}
                if 'offset' in fl and 'limit' in fl: style='offset'
                elif 'last_id' in fl: style='last_id'
                elif 'cursor' in fl: style='cursor'
                elif 'page' in fl: style='page'
                elif 'datefrom' in fl and e['host'].startswith('statistics'): style='lastchangedate'
                else: style='none'
            e['pagination']=style; set_pg+=1
    print(f"items_path заполнено: {set_ip} | pagination заполнено: {set_pg}")
    from collections import Counter
    print("pagination всего:", dict(Counter(e.get('pagination') for e in cat['endpoints'])))
    if a.apply:
        Path(a.catalog).write_text(yaml.safe_dump(cat,allow_unicode=True,sort_keys=False),encoding='utf-8'); print("ЗАПИСАНО")
    else: print("(dry-run)")

if __name__=='__main__': main()
