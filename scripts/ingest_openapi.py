#!/usr/bin/env python3
"""Ingest a bundled OpenAPI 3 document into a catalog (endpoints.yaml).

Generic successor of ingest_specs.py (WB) / ingest_ozon.py (Ozon): used for
Yandex Market (official spec: github.com/yandex-market/yandex-market-partner-api,
bundled with `redocly bundle`) and any future marketplace that ships OpenAPI.

    python3 scripts/ingest_openapi.py --spec ym.json --catalog yandex_mcp/endpoints.yaml \
        --prefix ym --host api.partner.market.yandex.ru \
        --doc-base https://yandex.ru/dev/market/partner-api/doc/ru/reference --apply

Additive and idempotent: existing records (by operation_id or method+path) are
never touched, so curated safety / keywords / items_path survive re-runs.

Safety is a conservative heuristic — GET→read, DELETE→destructive, PUT/PATCH→
write, POST by the operationId verb — and MUST be audited (see
tests/test_safety_catalog.py). A POST that only *reads* (getX, searchX,
calculateX, generateXReport) is read; anything else mutates.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

import yaml

READ_VERBS = ("get", "list", "search", "find", "calculate", "generate", "check",
              "fetch", "read", "download", "view", "show", "count")
DESTRUCTIVE = re.compile(r"delete|remove|cancel", re.I)
# Tags that describe a delivery model rather than a business area (Yandex).
NOISE_TAGS = {"dbs", "fbs", "fby", "express", "laas"}

# Human section names per path segment. Entity matching (core/entities.yaml)
# keys off Russian/English substrings of the section, so these are worded to
# land in the right entity (заказ → orders, поставк → supplies, реклам → ads…).
SECTION_MAPS: dict[str, dict[str, str]] = {
    "yandex": {
        "campaigns": "Магазины (кампании) продавца",
        "settings": "Настройки продавца",
        "orders": "Заказы",
        "returns": "Возвраты и невыкупы",
        "regions": "Регионы доставки",
        "delivery": "Доставка",
        "delivery-options": "Доставка",
        "return-delivery-options": "Доставка возвратов",
        "shipments": "Отгрузки и поставки (first-mile)",
        "first-mile": "Отгрузки и поставки (first-mile)",
        "supply-requests": "Заявки на поставку",
        "offers": "Товары",
        "offer-mappings": "Товары (каталог)",
        "offer-cards": "Карточки товаров (контент)",
        "hidden-offers": "Скрытые товары",
        "categories": "Категории",
        "category": "Категории",
        "offer-prices": "Цены",
        "price-quarantine": "Карантин цен",
        "promos": "Акции и продвижение",
        "bids": "Буст продаж и ставки (реклама)",
        "stocks": "Остатки",
        "warehouses": "Склады",
        "warehouse": "Склады",
        "outlets": "Точки продаж и ПВЗ (самовывоз)",
        "logistics-points": "Точки продаж и ПВЗ (самовывоз)",
        "goods-feedback": "Отзывы о товарах",
        "goods-feedback-advertiser": "Отзывы о товарах",
        "goods-questions": "Вопросы о товарах",
        "chats": "Чаты с покупателями",
        "chat": "Чаты с покупателями",
        "ratings": "Рейтинг и индекс качества",
        "stats": "Статистика заказов и товаров",
        "reports": "Отчёты",
        "tariffs": "Тарифы и комиссии",
        "auth": "Токен и доступ (пользователь)",
        "operations": "Статусы операций (система)",
    },
}


def snake(s: str) -> str:
    s = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", s)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def safety(method: str, oid: str, path: str) -> str:
    m = method.lower()
    if m == "delete":
        return "destructive"
    if m in ("put", "patch"):
        return "write"
    if m == "get":
        return "read"
    verb = snake(oid).split("_")[0] if oid else ""
    if DESTRUCTIVE.search(oid or "") or DESTRUCTIVE.search(path):
        return "destructive" if re.search(r"delete|remove", oid + path, re.I) else "write"
    if verb in READ_VERBS:
        return "read"
    return "write"


def section_of(path: str, tags: list[str]) -> str:
    """Business area from the path: strip /vN and the {campaignId}/{businessId}
    prefix, take the first segment. Falls back to a non-noise tag."""
    parts = [p for p in path.split("/") if p]
    parts = [p for p in parts if not re.fullmatch(r"v\d+", p)]
    while parts and (parts[0] in ("campaigns", "businesses") and len(parts) > 1
                     and parts[1].startswith("{")):
        parts = parts[2:]
    if parts and not parts[0].startswith("{"):
        return parts[0]
    for t in tags:
        if t not in NOISE_TAGS:
            return t
    return "general"


def resolve(spec: dict, obj):
    """Follow a local $ref once (bundled specs keep parameter refs)."""
    if isinstance(obj, dict) and "$ref" in obj:
        node = spec
        for part in obj["$ref"].lstrip("#/").split("/"):
            node = node.get(part, {}) if isinstance(node, dict) else {}
        return node
    return obj


def deref(spec: dict, node, depth: int = 0):
    """Resolve $ref chains (bundled specs still use component refs) and merge
    allOf so we can see the response's properties."""
    if depth > 12 or not isinstance(node, dict):
        return node if isinstance(node, dict) else {}
    if "$ref" in node:
        return deref(spec, resolve(spec, node), depth + 1)
    if "allOf" in node:
        merged: dict = {"properties": {}}
        for part in node["allOf"]:
            part = deref(spec, part, depth + 1)
            merged["properties"].update(part.get("properties") or {})
            if part.get("type"):
                merged["type"] = part["type"]
        return merged
    return node


def items_path_of(spec: dict, op: dict) -> str:
    """Dotted path to the main list in the 200 response (e.g. result.orders).
    Prefers a 'result' wrapper (Yandex). Empty when nothing obvious."""
    content = ((op.get("responses") or {}).get("200") or {}).get("content") or {}
    schema = (content.get("application/json") or {}).get("schema")
    if not schema:
        return ""

    def walk(node, prefix: list[str], depth: int) -> str:
        node = deref(spec, node)
        props = node.get("properties") or {}
        if node.get("type") == "array" and prefix:
            return ".".join(prefix)
        if depth >= 3:
            return ""
        # Arrays directly under this object: prefer non-meta names.
        arrays = [k for k, v in props.items()
                  if deref(spec, v).get("type") == "array" and k not in ("errors", "warnings")]
        if len(arrays) == 1:
            return ".".join(prefix + [arrays[0]])
        if len(arrays) > 1:
            return ""  # ambiguous → leave for a human
        for wrapper in ("result", "results", "data"):
            if wrapper in props:
                found = walk(props[wrapper], prefix + [wrapper], depth + 1)
                if found:
                    return found
        # single object child (e.g. result.offerMappings nested one level)
        objs = [k for k, v in props.items() if deref(spec, v).get("properties")]
        if len(objs) == 1:
            return walk(props[objs[0]], prefix + [objs[0]], depth + 1)
        return ""

    return walk(schema, [], 0)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--prefix", required=True)
    ap.add_argument("--host", required=True)
    ap.add_argument("--scope", default="seller")
    ap.add_argument("--doc-base", default="")
    ap.add_argument("--sections", default="", choices=["", *SECTION_MAPS],
                    help="named section map (human names per path segment)")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    spec = json.loads(Path(a.spec).read_text(encoding="utf-8"))
    cat_path = Path(a.catalog)
    cat = yaml.safe_load(cat_path.read_text(encoding="utf-8")) if cat_path.exists() else {}
    cat = cat or {}
    cat.setdefault("default_host", a.host)
    eps = cat.setdefault("endpoints", [])
    seen_oid = {e["operation_id"] for e in eps}
    seen_path = {(e["method"].upper(), e["path"]) for e in eps}

    added, by_safety, by_section = [], Counter(), Counter()
    for path, item in (spec.get("paths") or {}).items():
        shared_params = [resolve(spec, p) for p in item.get("parameters", [])]
        for method, op in item.items():
            if method.lower() not in ("get", "post", "put", "patch", "delete"):
                continue
            if not isinstance(op, dict):
                continue
            if (method.upper(), path) in seen_path:
                continue
            swid = op.get("operationId") or ""
            base = f"{a.prefix}_{snake(swid) if swid else snake(method + '_' + path)}"[:60]
            oid, i = base, 2
            while oid in seen_oid:
                oid = f"{base}_{i}"
                i += 1
            params = shared_params + [resolve(spec, p) for p in op.get("parameters", [])]
            query = [p["name"] for p in params if isinstance(p, dict) and p.get("in") == "query"]
            pagination = "page_token" if "pageToken" in query else "none"
            tags = op.get("tags") or []
            doc = ""
            if a.doc_base and swid:
                area = next((t for t in tags if t not in NOISE_TAGS), None) or section_of(path, tags)
                doc = f"{a.doc_base}/{area}/{swid}"
            body_hint = ""
            rb = op.get("requestBody")
            if isinstance(rb, dict):
                schema = (rb.get("content") or {}).get("application/json", {}).get("schema", {})
                ref = schema.get("$ref", "") if isinstance(schema, dict) else ""
                body_hint = ref.split("/")[-1] if ref else ("object" if schema else "")
            ipath = items_path_of(spec, op) if method.lower() in ("get", "post") else ""
            section = section_of(path, tags)
            if a.sections:
                section = SECTION_MAPS[a.sections].get(section, section)
            rec = {
                "operation_id": oid,
                "section": section,
                "method": method.upper(),
                "host": a.host,
                "path": path,
                "scope": a.scope,
                "safety": safety(method, swid, path),
                "pagination": pagination,
                "summary": (op.get("summary") or op.get("description") or "").strip()[:180],
                "doc": doc,
            }
            if ipath:
                rec["items_path"] = ipath
            p = {}
            if query:
                p["query"] = ", ".join(query)
            if body_hint:
                p["body"] = body_hint
            if p:
                rec["params"] = p
            # English aliases from the operationId so EN queries hit RU summaries.
            words = [w for w in snake(swid).split("_") if len(w) > 2 and w not in READ_VERBS]
            if words:
                rec["keywords"] = words
            eps.append(rec)
            added.append(rec)
            seen_oid.add(oid)
            seen_path.add((method.upper(), path))
            by_safety[rec["safety"]] += 1
            by_section[rec["section"]] += 1

    print(f"new: {len(added)} | catalog: {len(eps)}")
    print("safety:", dict(by_safety))
    print("sections:", dict(by_section.most_common(40)))
    if a.apply:
        cat_path.parent.mkdir(parents=True, exist_ok=True)
        cat_path.write_text(yaml.safe_dump(cat, allow_unicode=True, sort_keys=False),
                            encoding="utf-8")
        print("WRITTEN", cat_path)
    else:
        print("(dry-run)")


if __name__ == "__main__":
    main()
