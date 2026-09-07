#!/usr/bin/env python3
"""avito_mcp — MCP server for the Avito API (Авито для бизнеса).

Covers the seller-relevant sections of api.avito.ru — listings & stats,
stock management, orders (Авито Доставка), messenger, ratings & reviews,
promotion, autoload, user/balance — through schema-driven meta-tools
(search / describe / call / fetch_all) plus typed tools for everyday tasks.

Auth: OAuth2 client_credentials — POST https://api.avito.ru/token
(form-encoded client_id + client_secret) → Bearer token, cached and refreshed
by the core client. Get the pair at avito.ru → Для бизнеса → Интеграции → API.

Many methods take the seller's numeric user_id in the path; typed tools resolve
it once via /core/v1/accounts/self and cache it for the process lifetime.

Catalog: avito_mcp/endpoints.yaml, built by scripts/ingest_avito.py from the
per-section OpenAPI documents of the Avito developer portal.

Run:
    AVITO_CLIENT_ID=... AVITO_CLIENT_SECRET=... python -m avito_mcp.server
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

from core.client import MarketplaceClient, ServiceConfig
from core.entities import EntityIndex
from core.registry import Catalog
from core.safety import check_gate
from core.tools import register_cabinet_tools, register_generic_tools
from core.workflows import Workflows, register_workflow_tools
from core.transport import run as run_transport

CATALOG_PATH = Path(__file__).with_name("endpoints.yaml")
WORKFLOWS_PATH = Path(__file__).with_name("workflows.yaml")


def _build_headers(creds: dict[str, str]) -> dict[str, str]:
    # Auth is the bearer token injected by the OAuth client; only content-type here.
    return {"Content-Type": "application/json"}


AVITO_CONFIG = ServiceConfig(
    name="avito",
    scheme="https",
    fields=["client_id", "client_secret"],
    env_map={"client_id": "AVITO_CLIENT_ID", "client_secret": "AVITO_CLIENT_SECRET"},
    build_headers=_build_headers,
    whoami=("avito_get_user_info_self", ["name", "email"]),
    allowed_host_suffixes=[".avito.ru"],
    token_url="https://api.avito.ru/token",
    oauth_id_field="client_id",
    oauth_secret_field="client_secret",  # pragma: allowlist secret
    token_encoding="form",
)

mcp = FastMCP("avito_mcp")
entities = EntityIndex.load()
catalog = Catalog.from_yaml(CATALOG_PATH, entities=entities)
client = MarketplaceClient(AVITO_CONFIG)

register_generic_tools(
    mcp, svc="avito", client=client, catalog=catalog, entities=entities,
    key_help="avito.ru → Для бизнеса → Интеграции → API → client_id + client_secret "
             "(OAuth2 client_credentials).",
)
register_cabinet_tools(mcp, svc="avito", client=client, catalog=catalog)
register_workflow_tools(mcp, svc="avito", workflows=Workflows.from_yaml(WORKFLOWS_PATH))


def _j(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, default=str)


_user_id_cache: dict[str, int] = {}


async def _user_id() -> tuple[Optional[int], Optional[dict]]:
    """Seller's numeric id from /core/v1/accounts/self (cached per credentials)."""
    creds, _src = client.config.resolve_creds()
    key = creds.get("client_id", "")
    if key in _user_id_cache:
        return _user_id_cache[key], None
    resp = await client.call_spec(catalog.get("avito_get_user_info_self"))
    if not resp.get("ok"):
        return None, resp
    uid = (resp.get("data") or {}).get("id")
    if not isinstance(uid, int):
        return None, {"ok": False, "error": "unexpected_response",
                      "message": f"no numeric id in /core/v1/accounts/self: {str(resp.get('data'))[:200]}"}
    _user_id_cache[key] = uid
    return uid, None


def _ids(csv: str) -> list[int]:
    return [int(s) for s in csv.replace(";", ",").split(",") if s.strip()]


# --------------------------------------------------------------------------
# Typed convenience tools — everyday workflows.
# --------------------------------------------------------------------------
@mcp.tool(
    name="avito_whoami",
    annotations={"title": "Avito account", "readOnlyHint": True, "openWorldHint": True},
)
async def avito_whoami() -> str:
    """Authorized Avito account: id (needed as user_id in many methods), name,
    email, phone, profile_url. Also the cheapest way to verify the credentials.
    Returns JSON: {"ok": true, "data": {"id": ..., "name": ..., ...}}.
    """
    return _j(await client.call_spec(catalog.get("avito_get_user_info_self")))


@mcp.tool(
    name="avito_get_items",
    annotations={"title": "Avito listings", "readOnlyHint": True, "openWorldHint": True},
)
async def avito_get_items(status: str = "active", category: int = 0,
                          updated_from: str = "", page: int = 1, per_page: int = 50) -> str:
    """List the seller's listings (объявления): status, category, url
    (GET /core/v1/items). Max 25 requests/min.

    Args:
        status: active | removed | old | blocked | rejected (comma-separated ok).
        category: Avito category id filter, 0 = all.
        updated_from: YYYY-MM-DD lower bound on the listing update date.
        page: 1-based page number.
        per_page: page size (<100).
    Returns JSON: {"ok": true, "data": {"meta": {...}, "resources": [...]}}.
    For all pages use avito_fetch_all with avito_get_items_info.
    """
    q: dict = {"status": status, "page": max(1, page), "per_page": max(1, min(per_page, 99))}
    if category:
        q["category"] = category
    if updated_from:
        q["updatedAtFrom"] = updated_from
    return _j(await client.call_spec(catalog.get("avito_get_items_info"), query=q))


@mcp.tool(
    name="avito_get_orders",
    annotations={"title": "Avito orders", "readOnlyHint": True, "openWorldHint": True},
)
async def avito_get_orders(statuses: str = "", date_from: int = 0, page: int = 1,
                           limit: int = 20) -> str:
    """Orders placed with Авито Доставка (GET /order-management/1/orders).
    Business (B2C) sellers only.

    Args:
        statuses: comma-separated filter: on_confirmation, ready_to_ship,
            in_transit, canceled, delivered, on_return, in_dispute, closed.
        date_from: unix timestamp — only orders created after it.
        page: 1-based page number.
        limit: page size (<=20).
    Returns JSON: {"ok": true, "data": {"orders": [...], "hasMore": bool}}.
    Each order has availableActions (confirm / reject / setTrackNumber …) and
    schedules (deadlines such as confirmTill, shipTill).
    """
    q: dict = {"page": max(1, page), "limit": max(1, min(limit, 20))}
    if statuses:
        q["statuses"] = [s.strip() for s in statuses.split(",") if s.strip()]
    if date_from:
        q["dateFrom"] = date_from
    return _j(await client.call_spec(catalog.get("avito_get_orders"), query=q))


@mcp.tool(
    name="avito_get_stocks",
    annotations={"title": "Avito stocks", "readOnlyHint": True, "openWorldHint": True},
)
async def avito_get_stocks(item_ids: str) -> str:
    """Stock per listing (POST /stock-management/1/info): quantity,
    is_unlimited, is_out_of_stock. Up to 500 ids per call.

    Args:
        item_ids: comma-separated Avito listing ids.
    Returns JSON: {"ok": true, "data": {"stocks": [{"item_id", "quantity", ...}]}}.
    """
    body = {"item_ids": _ids(item_ids)}
    return _j(await client.call_spec(catalog.get("avito_get_stocks_info"), json_body=body))


@mcp.tool(
    name="avito_get_item_stats",
    annotations={"title": "Avito listing stats", "readOnlyHint": True, "openWorldHint": True},
)
async def avito_get_item_stats(item_ids: str, date_from: str, date_to: str,
                               period_grouping: str = "day") -> str:
    """Views / contacts / favorites per listing per period
    (POST /stats/v1/accounts/{user_id}/items). Up to 200 ids, 270 days deep.

    Args:
        item_ids: comma-separated listing ids.
        date_from: YYYY-MM-DD (inclusive).
        date_to: YYYY-MM-DD (inclusive).
        period_grouping: day | week | month.
    Returns JSON with result.items[].stats[] {date, uniqViews, uniqContacts, uniqFavorites}.
    """
    uid, err = await _user_id()
    if err:
        return _j(err)
    body = {"dateFrom": date_from, "dateTo": date_to, "itemIds": _ids(item_ids),
            "fields": ["uniqViews", "uniqContacts", "uniqFavorites"],
            "periodGrouping": period_grouping}
    return _j(await client.call_spec(catalog.get("avito_item_stats_shallow"),
                                     path_values={"user_id": uid}, json_body=body))


@mcp.tool(
    name="avito_get_reviews",
    annotations={"title": "Avito reviews", "readOnlyHint": True, "openWorldHint": True},
)
async def avito_get_reviews(offset: int = 0, limit: int = 50) -> str:
    """Published reviews on the seller with score, text, deal stage and the
    seller's answer (GET /ratings/v1/reviews). Use avito_get_ratings_info_v1
    via avito_call_method for the aggregate rating.

    Args:
        offset: pagination offset.
        limit: page size (<=50).
    Returns JSON: {"ok": true, "data": {"total": n, "reviews": [...]}}.
    """
    q = {"offset": max(0, offset), "limit": max(1, min(limit, 50))}
    return _j(await client.call_spec(catalog.get("avito_get_reviews_v1"), query=q))


@mcp.tool(
    name="avito_get_chats",
    annotations={"title": "Avito chats", "readOnlyHint": True, "openWorldHint": True},
)
async def avito_get_chats(unread_only: bool = False, item_ids: str = "",
                          limit: int = 50, offset: int = 0) -> str:
    """Buyer chats (GET /messenger/v2/accounts/{user_id}/chats). Requires the
    Messenger API to be enabled on the seller's Avito plan.

    Args:
        unread_only: only chats with unread messages.
        item_ids: comma-separated listing ids to filter chats by.
        limit: page size (<=100).
        offset: pagination offset (<=1000).
    Returns JSON: {"ok": true, "data": {"chats": [{"id", "context", "last_message", "users"}]}}.
    """
    uid, err = await _user_id()
    if err:
        return _j(err)
    q: dict = {"limit": max(1, min(limit, 100)), "offset": max(0, offset)}
    if unread_only:
        q["unread_only"] = "true"
    if item_ids:
        q["item_ids"] = item_ids
    return _j(await client.call_spec(catalog.get("avito_get_chats_v2"),
                                     path_values={"user_id": uid}, query=q))


@mcp.tool(
    name="avito_get_balance",
    annotations={"title": "Avito wallet balance", "readOnlyHint": True, "openWorldHint": True},
)
async def avito_get_balance() -> str:
    """Wallet balance: real money and bonuses (GET /core/v1/accounts/{user_id}/balance/).
    Returns JSON: {"ok": true, "data": {"real": ..., "bonus": ...}}.
    """
    uid, err = await _user_id()
    if err:
        return _j(err)
    return _j(await client.call_spec(catalog.get("avito_get_user_balance"),
                                     path_values={"user_id": uid}))


@mcp.tool(
    name="avito_update_price",
    annotations={"title": "Avito update listing price", "readOnlyHint": False,
                 "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def avito_update_price(item_id: int, price: int, confirm_write: bool = False) -> str:
    """Set the price of ONE listing (POST /core/v1/items/{item_id}/update_price). WRITE.

    Requires confirm_write=true. Goods, spare parts, cars, real estate only;
    max 150 requests/min.

    Args:
        item_id: Avito listing id.
        price: new price in roubles (integer).
        confirm_write: must be true to send.
    Returns JSON: {"ok": true, "data": {"result": {"success": true}}}.
    """
    gate = check_gate("write", confirm_write=confirm_write,
                      i_understand_this_modifies_data=True,
                      operation_id="avito_update_price",
                      endpoint="/core/v1/items/{item_id}/update_price")
    if gate:
        return _j(gate)
    return _j(await client.call_spec(catalog.get("avito_update_price"),
                                     path_values={"item_id": item_id},
                                     json_body={"price": int(price)}))


@mcp.tool(
    name="avito_update_stock",
    annotations={"title": "Avito update stock", "readOnlyHint": False,
                 "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def avito_update_stock(item_id: int, quantity: int, confirm_write: bool = False) -> str:
    """Set the available quantity of ONE listing (PUT /stock-management/1/stocks). WRITE.

    Requires confirm_write=true. quantity 0 hides the "buy with delivery" button.

    Args:
        item_id: Avito listing id.
        quantity: units available (0..999999).
        confirm_write: must be true to send.
    Returns JSON: {"ok": true, "data": {"stocks": [{"item_id", "success", "errors"}]}}.
    """
    gate = check_gate("write", confirm_write=confirm_write,
                      i_understand_this_modifies_data=True,
                      operation_id="avito_update_stock",
                      endpoint="/stock-management/1/stocks")
    if gate:
        return _j(gate)
    body = {"stocks": [{"item_id": item_id, "quantity": max(0, int(quantity))}]}
    return _j(await client.call_spec(catalog.get("avito_update_stocks"), json_body=body))


def main() -> None:
    """Console entry point: stdio by default, HTTP with MCP_TRANSPORT=http."""
    run_transport(mcp)


if __name__ == "__main__":
    main()
