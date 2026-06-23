"""Auto-pagination walker shared by both servers.

Marketplaces use several cursor styles. This walker covers the common,
machine-friendly ones so an agent can ask for "all" rows without hand-rolling
loops. Anything exotic can still be paged manually via the generic executor.

Supported styles (EndpointSpec.pagination):
- offset          : limit/offset (in body for POST, query for GET); stop on short page
- last_id         : Ozon — body filter, response result.last_id
- cursor          : Ozon v4/v5 — top-level "cursor" token + "total"
- page            : body page/page_size, response result.page_count
- lastchangedate  : WB statistics — query dateFrom = last row's lastChangeDate
- none            : single request

Item paths vary per endpoint (result.items, items, result.rows,
result.operations, result.postings, products, ...). The walker reads
EndpointSpec.items_path unless overridden.

Each style has a small adapter. The walker guards against infinite loops by
detecting a repeated cursor and by honouring max_items / max_pages.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from .client import MarketplaceClient
from .errors import make_error
from .registry import EndpointSpec

DEFAULT_MAX_ITEMS = 10_000
DEFAULT_MAX_PAGES = 200


def _dig(obj: Any, dotted: str) -> Any:
    cur = obj
    for part in dotted.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


async def fetch_all(
    client: MarketplaceClient,
    spec: EndpointSpec,
    *,
    base_query: Optional[dict[str, Any]] = None,
    base_body: Optional[dict[str, Any]] = None,
    path_values: Optional[dict[str, Any]] = None,
    items_path: Optional[str] = None,
    limit: int = 1000,
    max_items: int = DEFAULT_MAX_ITEMS,
    max_pages: int = DEFAULT_MAX_PAGES,
) -> dict:
    """Walk pages until exhausted, truncated, or limits hit.

    Returns {"ok": True, "items": [...], "total_fetched": n, "pages_fetched": p,
    "truncated": bool} or the canonical error envelope on the first failure.
    """
    style = spec.pagination or "none"
    ipath = items_path or spec.items_path
    is_get = spec.method.upper() == "GET"
    items: list[Any] = []
    pages = 0
    query = dict(base_query or {})
    body = dict(base_body or {})
    seen_cursor: Optional[str] = None

    while True:
        # paging params go in the query for GET, the body for POST
        loc = query if is_get else body
        if style == "offset":
            loc.setdefault("limit", limit)
            loc["offset"] = len(items)
        elif style == "cursor":
            loc.setdefault("limit", limit)
            if seen_cursor:
                loc["cursor"] = seen_cursor
        elif style == "last_id":
            loc.setdefault("limit", limit)
            if seen_cursor:
                loc["last_id"] = seen_cursor
        elif style == "page":
            body.setdefault("page_size", limit)
            body["page"] = pages + 1

        resp = await client.call_spec(
            spec, path_values=path_values, query=query or None, json_body=body or None
        )
        if not resp.get("ok"):
            return resp  # propagate error envelope

        data = resp["data"]
        page_items = _dig(data, ipath)
        if page_items is None and isinstance(data, list):
            page_items = data
        page_items = page_items or []
        items.extend(page_items)
        pages += 1

        truncated = len(items) >= max_items or pages >= max_pages
        if truncated:
            return _result(items[:max_items], pages, truncated=True)
        if not page_items:
            return _result(items, pages, truncated=False)

        # advance cursor per style
        if style == "offset":
            if len(page_items) < loc.get("limit", limit):
                return _result(items, pages, truncated=False)
        elif style == "cursor":
            cur = _dig(data, "cursor")
            total = _dig(data, "total")
            if total is not None and len(items) >= int(total):
                return _result(items, pages, truncated=False)
            if not cur or cur == seen_cursor:
                return _result(items, pages, truncated=False)
            seen_cursor = cur
        elif style == "last_id":
            last_id = _dig(data, "result.last_id") or _dig(data, "last_id")
            if not last_id or last_id == seen_cursor:
                return _result(items, pages, truncated=False)
            seen_cursor = last_id
        elif style == "page":
            page_count = _dig(data, "result.page_count") or _dig(data, "page_count")
            if page_count and pages >= int(page_count):
                return _result(items, pages, truncated=False)
        elif style == "lastchangedate":
            last = page_items[-1]
            lcd = last.get("lastChangeDate") if isinstance(last, dict) else None
            if not lcd or lcd == seen_cursor:
                return _result(items, pages, truncated=False)
            seen_cursor = lcd
            query["dateFrom"] = lcd
        else:  # none / unsupported -> single page
            return _result(items, pages, truncated=False)


def _result(items: list[Any], pages: int, *, truncated: bool) -> dict:
    return {
        "ok": True,
        "items": items,
        "total_fetched": len(items),
        "pages_fetched": pages,
        "truncated": truncated,
    }
