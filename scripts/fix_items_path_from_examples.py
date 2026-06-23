#!/usr/bin/env python3
"""Offline-fix items_path using RESPONSE EXAMPLES from OpenAPI specs.

items_path in the catalogs was derived from response SCHEMAS. Where the spec's
schema disagrees with the real response shape, items_path can be wrong. OpenAPI
specs often carry response *examples* (responses."200".content."application/json".
example | .examples | schema.example | $ref->example) that show the real shape.

For each catalog record matched by (method, path) that has items_path:
  - extract a concrete 200 example object,
  - locate arrays in it (dotted path, depth<=3),
  - if the current items_path does NOT dig to a list in the example AND the
    example contains exactly ONE array -> rewrite items_path to that path.
Otherwise leave items_path untouched (a wrong items_path is worse than absent,
so we only change on unambiguous evidence).

Curated records (non-empty 'doc' or 'keywords') are also only ever touched on
this same unambiguous single-array evidence.

Pure offline: reads specs from /tmp, never calls a marketplace API. Idempotent.

Usage:
  python3 scripts/fix_items_path_from_examples.py [--dry-run] [--verbose]

Specs expected (auto-downloaded by the caller, or pre-cached) at:
  /tmp/wbspecs/<NN-name>.yaml  (14 WB specs, eslazarev/wildberries-sdk)
  /tmp/seller_swagger.json     (Ozon seller, PCDCK/ozon-mcp)
"""
from __future__ import annotations
import sys, json, glob, argparse
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML required: pip install pyyaml")

REPO = Path(__file__).resolve().parent.parent
WB_SPEC_GLOB = "/tmp/wbspecs/*.yaml"
OZON_SPEC = "/tmp/seller_swagger.json"


# ---------- spec helpers ----------

def resolve_ref(spec: dict, ref: str, depth: int = 0):
    """Resolve a local #/... JSON pointer. Returns the node or None."""
    if depth > 8 or not isinstance(ref, str) or not ref.startswith("#/"):
        return None
    cur = spec
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    # one level of indirection if the target is itself a pure $ref
    if isinstance(cur, dict) and set(cur.keys()) == {"$ref"}:
        return resolve_ref(spec, cur["$ref"], depth + 1)
    return cur


def get_200_example(spec: dict, op: dict):
    """Return a concrete example object for op's 200 response, or None.

    Sources, in priority order:
      content.<mime>.example
      content.<mime>.examples.<first>.value  (value may be inline or a $ref)
      content.<mime>.schema.example
      content.<mime>.schema.$ref -> resolved.example
    """
    resps = op.get("responses", {}) or {}
    resp = resps.get("200") or resps.get(200)
    if not isinstance(resp, dict):
        return None
    content = resp.get("content", {}) or {}
    cobj = content.get("application/json") or (
        next(iter(content.values())) if content else None
    )
    if not isinstance(cobj, dict):
        return None

    if "example" in cobj:
        return cobj["example"]

    exs = cobj.get("examples")
    if isinstance(exs, dict) and exs:
        first = next(iter(exs.values()))
        if isinstance(first, dict):
            if "$ref" in first:
                first = resolve_ref(spec, first["$ref"]) or {}
            if isinstance(first, dict) and "value" in first:
                return first["value"]

    sch = cobj.get("schema")
    if isinstance(sch, dict):
        if "example" in sch:
            return sch["example"]
        if "$ref" in sch:
            r = resolve_ref(spec, sch["$ref"])
            if isinstance(r, dict) and "example" in r:
                return r["example"]
    return None


# ---------- example introspection ----------

def dig(obj, dotted: str):
    """Walk a dotted path through dicts. Returns the node or None."""
    cur = obj
    for p in (dotted or "").split("."):
        if p == "":
            continue
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return None
    return cur


def find_arrays(obj, prefix="", depth=0, out=None):
    """Collect (dotted_path, length) of every list reachable through dicts,
    up to depth 3. Lists nested inside list elements are not traversed."""
    if out is None:
        out = []
    if depth > 3 or not isinstance(obj, dict):
        return out
    for k, v in obj.items():
        path = prefix + k
        if isinstance(v, list):
            out.append((path, len(v)))
        elif isinstance(v, dict):
            find_arrays(v, path + ".", depth + 1, out)
    return out


# ---------- spec indexing ----------

def index_spec(spec: dict) -> dict:
    """Map (METHOD, path) -> example object (only where a 200 example exists)."""
    idx = {}
    for p, methods in (spec.get("paths", {}) or {}).items():
        if not isinstance(methods, dict):
            continue
        for m, op in methods.items():
            if not isinstance(op, dict):
                continue
            ex = get_200_example(spec, op)
            if ex is not None:
                idx[(m.upper(), p)] = ex
    return idx


def build_index():
    wb_idx, oz_idx = {}, {}
    wb_files = sorted(glob.glob(WB_SPEC_GLOB))
    for f in wb_files:
        try:
            spec = yaml.safe_load(Path(f).read_text())
        except Exception as e:
            print(f"  WARN: cannot parse {f}: {e}")
            continue
        if isinstance(spec, dict):
            wb_idx.update(index_spec(spec))
    if Path(OZON_SPEC).exists():
        oz = json.loads(Path(OZON_SPEC).read_text())
        oz_idx = index_spec(oz)
    else:
        print(f"  WARN: {OZON_SPEC} missing -> Ozon uncovered")
    return wb_idx, oz_idx, len(wb_files)


# ---------- core fix ----------

def fix_catalog(label, cat_path: Path, example_idx: dict, dry_run: bool, verbose: bool):
    cat = yaml.safe_load(cat_path.read_text())
    eps = cat["endpoints"]

    with_ip = [e for e in eps if e.get("items_path")]
    matched = unambiguous = fixed = already_ok = no_arrays = ambiguous = 0
    no_example = 0
    changes = []

    for e in eps:
        ip = e.get("items_path")
        if not ip:
            continue
        key = (e["method"].upper(), e["path"])
        ex = example_idx.get(key)
        if ex is None:
            no_example += 1
            continue
        matched += 1

        # Does the current items_path already dig to a list in the example?
        if isinstance(ex, dict):
            dug = dig(ex, ip)
        elif isinstance(ex, list):
            # example IS the array at root; items_path should be "" but we are
            # conservative and do not invent a root marker -> treat as ok.
            dug = ex
        else:
            dug = None
        if isinstance(dug, list):
            already_ok += 1
            continue

        # current items_path is wrong against the example; look for THE array.
        arrays = find_arrays(ex) if isinstance(ex, dict) else []
        if not arrays:
            no_arrays += 1
            if verbose:
                print(f"  [{label}] no array in example  {key[1]} ip={ip}")
            continue
        if len(arrays) != 1:
            ambiguous += 1
            if verbose:
                print(f"  [{label}] ambiguous {key[1]} ip={ip} "
                      f"arrays={[a[0] for a in arrays][:5]}")
            continue

        unambiguous += 1
        real = arrays[0][0]
        if real == ip:
            already_ok += 1
            continue
        curated = bool(e.get("doc")) or bool(e.get("keywords"))
        changes.append((key[1], ip, real, curated))
        if not dry_run:
            e["items_path"] = real
        fixed += 1

    if changes:
        print(f"\n  [{label}] {'WOULD FIX' if dry_run else 'FIXED'} {len(changes)}:")
        for path, old, new, curated in changes:
            tag = " (curated)" if curated else ""
            print(f"    {path}: {old} -> {new}{tag}")

    if not dry_run and changes:
        cat_path.write_text(
            yaml.safe_dump(cat, allow_unicode=True, sort_keys=False)
        )

    print(f"\n  [{label}] records_with_items_path={len(with_ip)} "
          f"no_example(uncovered)={no_example} matched_example={matched} "
          f"already_ok={already_ok} single_array_evidence={unambiguous} "
          f"no_array={no_arrays} ambiguous={ambiguous} fixed={fixed}")
    return fixed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    wb_idx, oz_idx, wb_n = build_index()
    print(f"Indexed specs: WB files={wb_n} (200-examples={len(wb_idx)}), "
          f"Ozon 200-examples={len(oz_idx)}")

    total = 0
    total += fix_catalog("WB", REPO / "wb_mcp/endpoints.yaml", wb_idx,
                         args.dry_run, args.verbose)
    total += fix_catalog("OZON", REPO / "ozon_mcp/endpoints.yaml", oz_idx,
                         args.dry_run, args.verbose)
    print(f"\nTOTAL {'would-fix' if args.dry_run else 'fixed'}: {total}")


if __name__ == "__main__":
    main()
