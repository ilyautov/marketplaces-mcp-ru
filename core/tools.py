"""Generic MCP tool layer, registered identically for every marketplace.

Given a FastMCP instance, a MarketplaceClient and a Catalog, this wires up the
schema-driven meta-tools that turn hundreds of endpoints into a handful of
high-leverage tools:

    {svc}_check_auth        verify credentials are present (no secrets echoed)
    {svc}_list_sections     browse the API by section
    {svc}_get_section       list endpoints in one section
    {svc}_search_methods    token search across the catalog (RU/EN)
    {svc}_describe_method    full spec for one operation_id
    {svc}_call_method       execute a catalog endpoint (safety-gated)
    {svc}_call_raw          execute ANY path (full coverage, verb-gated)
    {svc}_fetch_all         auto-paginate a catalog endpoint

Typed convenience tools live in each service's server.py and call the same
client underneath.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

from .client import MarketplaceClient
from .paginate import fetch_all as _fetch_all
from .registry import Catalog
from .safety import check_gate, infer_safety


def _j(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, default=str)


def register_generic_tools(
    mcp: FastMCP,
    *,
    svc: str,
    client: MarketplaceClient,
    catalog: Catalog,
    key_help: str = "",
    entities: Optional[Any] = None,
) -> None:
    """Register the 8 generic tools under the `{svc}_` prefix.

    key_help: human note on where to obtain the API keys (shown by check_auth).
    entities: EntityIndex instance (optional); enables the *_map tool overview.
    """

    @mcp.tool(
        name=f"{svc}_check_auth",
        annotations={"title": f"{svc.upper()} check credentials",
                     "readOnlyHint": True, "openWorldHint": False},
    )
    async def check_auth() -> str:
        """Check whether the required credentials are present in the environment.

        Does NOT reveal secret values — only reports which variables are set.
        Returns JSON: {"ready": bool, "missing": [str], "required": [str]}.
        """
        creds, source = client.config.resolve_creds()
        missing = [f for f in client.config.fields if not creds.get(f)]
        cabinets = client.config.store.list_cabinets(client.config.name)
        return _j({
            "ready": not missing,
            "active_cabinet": cabinets["active"],
            "source": source,  # cabinet name, "env", or "none"
            "cabinets": cabinets["cabinets"],
            "missing_fields": missing,
            "hint": (f"Add a cabinet with {svc}_add_cabinet, switch with "
                     f"{svc}_use_cabinet, or run install.py."),
            "where_to_get_keys": key_help,
        })

    @mcp.tool(
        name=f"{svc}_list_sections",
        annotations={"title": f"{svc.upper()} list sections",
                     "readOnlyHint": True, "openWorldHint": False},
    )
    async def list_sections() -> str:
        """List API sections and how many catalog endpoints each contains."""
        return _j({"sections": catalog.sections(), "total_endpoints": len(catalog.all())})

    @mcp.tool(
        name=f"{svc}_get_section",
        annotations={"title": f"{svc.upper()} get section",
                     "readOnlyHint": True, "openWorldHint": False},
    )
    async def get_section(section: str) -> str:
        """List all endpoints in one section.

        Args:
            section: section name (see {svc}_list_sections), e.g. "statistics".
        Returns JSON list of {operation_id, method, path, safety, summary}.
        """
        specs = catalog.in_section(section)
        if not specs:
            return _j({"error": "not_found", "message": f"No section '{section}'.",
                       "available": list(catalog.sections().keys())})
        return _j({"section": section, "endpoints": [s.to_summary_dict() for s in specs]})

    @mcp.tool(
        name=f"{svc}_search_methods",
        annotations={"title": f"{svc.upper()} search methods",
                     "readOnlyHint": True, "openWorldHint": False},
    )
    async def search_methods(query: str, limit: int = 15) -> str:
        """Search the endpoint catalog by keyword (works in Russian and English).

        Args:
            query: free text, e.g. "остатки", "stocks", "update price".
            limit: max results (1-50).
        Returns JSON list of matching endpoints (best first).
        """
        limit = max(1, min(50, limit))
        specs = catalog.search(query, limit=limit)
        return _j({"query": query, "count": len(specs),
                   "results": [s.to_summary_dict() for s in specs]})

    @mcp.tool(
        name=f"{svc}_map",
        annotations={"title": f"{svc.upper()} capabilities map",
                     "readOnlyHint": True, "openWorldHint": False},
    )
    async def entity_map(entity: str = "") -> str:
        """The big picture: business entities this API covers and the go-to
        methods for each. Call with no args to see the whole map ("you are
        here"); pass entity="reviews" (or stocks/prices/orders/…) to list every
        method of one entity. Use this before guessing — it orients you fast.
        """
        ents = entities.entities if entities is not None else []
        by_key: dict[str, list] = {}
        for s in catalog.all():
            for k in (s.entity or ["other"]):
                by_key.setdefault(k, []).append(s)
        if entity:
            specs = by_key.get(entity, [])
            return _j({"entity": entity, "count": len(specs),
                       "methods": [s.to_summary_dict() for s in specs]})
        out = []
        for e in ents:
            specs = by_key.get(e["key"], [])
            if not specs:
                continue
            headline = [s for s in specs if s.operation_id in e.get("headline", [])]
            # Fallback: surface read methods first so the map answers "how do I
            # see X" before "how do I change/delete X".
            ordered = sorted(specs, key=lambda s: 0 if s.safety == "read" else 1)
            shown = headline or ordered[:5]
            out.append({
                "key": e["key"], "title_ru": e["title_ru"],
                "title_en": e["title_en"], "synonyms": e["synonyms"],
                "method_count": len(specs),
                "headline": [s.to_summary_dict() for s in shown],
            })
        if by_key.get("other"):
            out.append({"key": "other", "title_ru": "Прочее", "title_en": "Other",
                        "synonyms": [], "method_count": len(by_key["other"]),
                        "headline": []})
        return _j({"service": svc, "entities": out})

    @mcp.tool(
        name=f"{svc}_describe_method",
        annotations={"title": f"{svc.upper()} describe method",
                     "readOnlyHint": True, "openWorldHint": False},
    )
    async def describe_method(operation_id: str) -> str:
        """Return the full catalog record for one endpoint: method, host, path,
        scope, safety level, pagination style, rate limit, params and doc URL."""
        spec = catalog.get(operation_id)
        if not spec:
            hits = catalog.search(operation_id, limit=5)
            return _j({"error": "not_found", "operation_id": operation_id,
                       "did_you_mean": [s.operation_id for s in hits]})
        return _j({
            "operation_id": spec.operation_id, "section": spec.section,
            "entity": spec.entity,
            "method": spec.method, "host": spec.host, "path": spec.path,
            "path_params": spec.path_params, "scope": spec.scope,
            "safety": spec.safety, "pagination": spec.pagination,
            "rate_limit": spec.rate_limit, "summary": spec.summary,
            "params": spec.params, "doc": spec.doc,
        })

    @mcp.tool(
        name=f"{svc}_call_method",
        annotations={"title": f"{svc.upper()} call catalog method",
                     "readOnlyHint": False, "destructiveHint": True,
                     "openWorldHint": True},
    )
    async def call_method(
        operation_id: str,
        path_values: Optional[dict] = None,
        query: Optional[dict] = None,
        body: Optional[dict] = None,
        confirm_write: bool = False,
        i_understand_this_modifies_data: bool = False,
    ) -> str:
        """Execute one catalog endpoint by operation_id.

        Read endpoints run immediately. WRITE endpoints require confirm_write=true.
        DESTRUCTIVE endpoints require confirm_write=true AND
        i_understand_this_modifies_data=true (nothing is sent otherwise).

        Args:
            operation_id: id from the catalog (see {svc}_search_methods).
            path_values: values for {placeholders} in the path.
            query: query-string parameters.
            body: JSON request body.
            confirm_write: required for write/destructive operations.
            i_understand_this_modifies_data: required for destructive operations.
        Returns JSON: {"ok": true, "status", "data"} or the error envelope.
        """
        spec = catalog.get(operation_id)
        if not spec:
            hits = catalog.search(operation_id, limit=5)
            return _j({"error": "not_found", "operation_id": operation_id,
                       "did_you_mean": [s.operation_id for s in hits]})
        # Defense in depth: never let a catalog `read` weaken the gate below the
        # HTTP verb's floor (a mislabelled PUT/PATCH/DELETE must still be gated).
        gate = check_gate(
            infer_safety(spec.method, spec.safety), confirm_write=confirm_write,
            i_understand_this_modifies_data=i_understand_this_modifies_data,
            operation_id=spec.operation_id, endpoint=spec.path,
        )
        if gate:
            return _j(gate)
        resp = await client.call_spec(
            spec, path_values=path_values, query=query, json_body=body
        )
        return _j(resp)

    @mcp.tool(
        name=f"{svc}_call_raw",
        annotations={"title": f"{svc.upper()} call raw path",
                     "readOnlyHint": False, "destructiveHint": True,
                     "openWorldHint": True},
    )
    async def call_raw(
        method: str,
        path: str,
        host: Optional[str] = None,
        query: Optional[dict] = None,
        body: Optional[dict] = None,
        confirm_write: bool = False,
        i_understand_this_modifies_data: bool = False,
    ) -> str:
        """Execute ANY endpoint, even ones not in the catalog (full API coverage).

        Safety is inferred from the HTTP verb: GET=read, POST/PUT/PATCH=write,
        DELETE=destructive. Same confirmation rules as {svc}_call_method.

        Args:
            method: HTTP verb (GET/POST/PUT/PATCH/DELETE).
            path: full path beginning with '/', e.g. "/api/v1/supplier/sales".
            host: host override; defaults to the service's default host.
            query: query-string parameters.
            body: JSON request body.
            confirm_write / i_understand_this_modifies_data: confirmations.
        Returns JSON: {"ok": true, "status", "data"} or the error envelope.
        """
        safety = infer_safety(method, None)
        gate = check_gate(
            safety, confirm_write=confirm_write,
            i_understand_this_modifies_data=i_understand_this_modifies_data,
            endpoint=path,
        )
        if gate:
            return _j(gate)
        resp = await client.request(
            method, host or catalog.default_host, path, query=query, json_body=body
        )
        return _j(resp)

    @mcp.tool(
        name=f"{svc}_fetch_all",
        annotations={"title": f"{svc.upper()} fetch all pages",
                     "readOnlyHint": True, "openWorldHint": True},
    )
    async def fetch_all_tool(
        operation_id: str,
        query: Optional[dict] = None,
        body: Optional[dict] = None,
        path_values: Optional[dict] = None,
        items_path: Optional[str] = None,
        limit: int = 1000,
        max_items: int = 10000,
    ) -> str:
        """Auto-paginate a read endpoint and return every row in one response.

        Handles offset, last_id, cursor (Ozon v4/v5), page and WB lastChangeDate
        styles. The array path is taken from the catalog automatically.

        Args:
            operation_id: a read endpoint from the catalog.
            query / body / path_values: base parameters (cursor fields are managed).
            items_path: override the array path (default: the endpoint's own).
            limit: page size to request.
            max_items: hard cap to protect context (default 10000).
        Returns JSON: {"ok", "items", "total_fetched", "pages_fetched", "truncated"}.
        """
        spec = catalog.get(operation_id)
        if not spec:
            return _j({"error": "not_found", "operation_id": operation_id})
        # Verb-floor defense in depth (same as call_method): a mutating verb
        # mislabelled `read` in the catalog must not be looped over unconfirmed.
        if infer_safety(spec.method, spec.safety) != "read":
            return _j({"error": "invalid_params",
                       "message": "fetch_all only runs read endpoints; "
                                  f"{operation_id} is a {spec.method} write."})
        resp = await _fetch_all(
            client, spec, base_query=query, base_body=body, path_values=path_values,
            items_path=items_path, limit=limit, max_items=max_items,
        )
        return _j(resp)


def _dig(data: Any, dotted: str) -> Any:
    """Follow a dotted path into nested dicts; return None if any hop misses."""
    cur = data
    for part in dotted.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


async def fetch_shop_name(catalog: Optional[Catalog], client: MarketplaceClient,
                          creds: dict) -> Optional[str]:
    """Best-effort shop name from the marketplace's seller-info endpoint, using
    the given (possibly not-yet-stored) creds. Returns None on any problem —
    never raises. A failure here never blocks saving the key (the token may
    simply lack the seller-info scope)."""
    whoami = getattr(client.config, "whoami", None)
    if not whoami or catalog is None:
        return None
    op_id, name_fields = whoami
    spec = catalog.get(op_id)
    if spec is None:
        return None
    try:
        body = None if spec.method.upper() in ("GET", "HEAD") else {}
        resp = await client.call_spec(spec, json_body=body, creds_override=creds)
    except Exception:  # noqa: BLE001 — naming is best-effort, never fatal
        return None
    if not isinstance(resp, dict) or not resp.get("ok"):
        return None
    data = resp.get("data")
    for f in name_fields:
        val = _dig(data, f)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def _consent_block(svc: str, consent: bool) -> Optional[dict]:
    """Return an error dict if the chat-secret consent flag is not set, else None.

    Putting a key into a chat tool means it lands in the transcript. We require
    explicit acknowledgement and point at the safe door (the installer)."""
    if consent:
        return None
    return {
        "error": "consent_required",
        "message": (
            "This puts the API key into the chat transcript (the provider keeps "
            "chat history). If that's acceptable — use a scoped key and rotate it "
            "if exposed — call again with i_understand_key_goes_to_chat=true. "
            f"Safer alternative (key never enters chat): run the installer "
            f"(install.py / double-click)."),
        "safe_alternative": "installer",
    }


async def _store_key_core(*, config, catalog: Optional[Catalog],
                          client: MarketplaceClient, credentials: dict,
                          cabinet: str, consent: bool) -> dict:
    """Shared logic for the consented, auto-naming chat key tools. Testable
    without the MCP layer. Resolution order for the target cabinet:
    explicit name -> active cabinet -> shop name from API -> "main"."""
    block = _consent_block(config.name, consent)
    if block:
        return block
    missing = [f for f in config.fields if not credentials.get(f)]
    if missing:
        return {"error": "invalid_params",
                "message": f"Missing required field(s): {', '.join(missing)}.",
                "fields_needed": config.fields}
    clean = {f: str(credentials[f]) for f in config.fields}
    shop = await fetch_shop_name(catalog, client, clean)
    active = config.store.list_cabinets(config.name).get("active")
    target = cabinet or active or shop or "main"
    config.store.add_cabinet(config.name, target, clean, make_active=True)
    info = config.store.list_cabinets(config.name)
    return {
        "ok": True,
        "cabinet": target,
        "shop_name": shop,
        "validated": shop is not None,
        "note": (f"Shop confirmed: {shop}." if shop else
                 "Saved. Couldn't fetch the shop name (the key may lack that "
                 "scope, or the lookup isn't live-verified for this marketplace) "
                 "— the key is stored anyway."),
        "active": info["active"],
        "cabinets": info["cabinets"],
    }


def register_cabinet_tools(mcp: FastMCP, *, svc: str, client: MarketplaceClient,
                           catalog: Optional[Catalog] = None) -> None:
    """Register cabinet-management tools so students can add/switch credentials
    from chat without editing files. Keys are stored locally (chmod 600)."""
    config = client.config

    @mcp.tool(
        name=f"{svc}_list_cabinets",
        annotations={"title": f"{svc.upper()} list cabinets",
                     "readOnlyHint": True, "openWorldHint": False},
    )
    async def list_cabinets() -> str:
        """List configured cabinets for this marketplace and which one is active.

        Returns JSON: {"active": str|null, "cabinets": [names], "fields_needed": [...]}.
        Secret values are never returned.
        """
        info = config.store.list_cabinets(config.name)
        return _j({**info, "fields_needed": config.fields})

    @mcp.tool(
        name=f"{svc}_add_cabinet",
        annotations={"title": f"{svc.upper()} add cabinet",
                     "readOnlyHint": False, "destructiveHint": False,
                     "idempotentHint": True, "openWorldHint": False},
    )
    async def add_cabinet(credentials: dict, name: str = "",
                          i_understand_key_goes_to_chat: bool = False) -> str:
        """Add or update a cabinet (a named set of API credentials), from chat.

        ⚠️ This puts the key into the chat transcript — requires
        i_understand_key_goes_to_chat=true. The terminal-free safe alternative is
        the installer (install.py / double-click), where the key never enters chat.

        Args:
            credentials: dict with the required fields for this service
                ({fields}). For Ozon: {{"client_id": "...", "api_key": "..."}};
                for WB: {{"token": "..."}}.
            name: optional label. If omitted, the cabinet is named after the real
                shop name fetched from the marketplace (falls back to "main").
            i_understand_key_goes_to_chat: must be true to proceed.
        Saved to ~/.marketplace-mcp/cabinets.json (local, chmod 600), never echoed.
        """
        res = await _store_key_core(
            config=config, catalog=catalog, client=client,
            credentials=credentials, cabinet=name,
            consent=i_understand_key_goes_to_chat)
        return _j(res)

    @mcp.tool(
        name=f"{svc}_set_key",
        annotations={"title": f"{svc.upper()} set / rotate key",
                     "readOnlyHint": False, "destructiveHint": False,
                     "idempotentHint": True, "openWorldHint": False},
    )
    async def set_key(credentials: dict, cabinet: str = "",
                      i_understand_key_goes_to_chat: bool = False) -> str:
        """Change / rotate the API key from chat (e.g. the old one expired or
        leaked).

        ⚠️ The key goes into the chat transcript — requires
        i_understand_key_goes_to_chat=true. The safe, terminal-free alternative
        is the installer, where the key never enters chat. Use a scoped key and
        rotate it in the seller cabinet if it was exposed.

        Args:
            credentials: dict with the required fields ({fields}).
            cabinet: which cabinet to update. Default: the active one (so "my key
                expired" just works). If there is none, the cabinet is named from
                the marketplace's shop name, else "main".
            i_understand_key_goes_to_chat: must be true to proceed.
        On success the key is validated against the marketplace and the shop name
        is reported. Saved locally (chmod 600), never echoed back.
        """
        res = await _store_key_core(
            config=config, catalog=catalog, client=client,
            credentials=credentials, cabinet=cabinet,
            consent=i_understand_key_goes_to_chat)
        return _j(res)

    @mcp.tool(
        name=f"{svc}_use_cabinet",
        annotations={"title": f"{svc.upper()} switch cabinet",
                     "readOnlyHint": False, "idempotentHint": True,
                     "openWorldHint": False},
    )
    async def use_cabinet(name: str) -> str:
        """Switch the active cabinet. Subsequent API calls use its credentials.

        Args:
            name: the cabinet to activate (see {svc}_list_cabinets).
        """
        ok = config.store.set_active(config.name, name)
        if not ok:
            info = config.store.list_cabinets(config.name)
            return _j({"error": "not_found", "name": name,
                       "available": info["cabinets"]})
        return _j({"ok": True, "active": name})

    @mcp.tool(
        name=f"{svc}_remove_cabinet",
        annotations={"title": f"{svc.upper()} remove cabinet",
                     "readOnlyHint": False, "destructiveHint": True,
                     "openWorldHint": False},
    )
    async def remove_cabinet(name: str) -> str:
        """Delete a stored cabinet. If it was active, another becomes active.

        Args:
            name: the cabinet to remove.
        """
        ok = config.store.remove_cabinet(config.name, name)
        info = config.store.list_cabinets(config.name)
        return _j({"ok": ok, "removed": name if ok else None,
                   "active": info["active"], "cabinets": info["cabinets"]})
