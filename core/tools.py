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
) -> None:
    """Register the 8 generic tools under the `{svc}_` prefix.

    key_help: human note on where to obtain the API keys (shown by check_auth).
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
        missing = client.config.missing_env()
        return _j({
            "ready": not missing,
            "required": client.config.required_env,
            "missing": missing,
            "hint": ("Credentials are read from the MCP server's env block. "
                     "Run install.py to set them, or edit the Claude config."),
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
        gate = check_gate(
            spec.safety, confirm_write=confirm_write,
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
        if spec.safety != "read":
            return _j({"error": "invalid_params",
                       "message": "fetch_all only runs read endpoints."})
        resp = await _fetch_all(
            client, spec, base_query=query, base_body=body, path_values=path_values,
            items_path=items_path, limit=limit, max_items=max_items,
        )
        return _j(resp)
