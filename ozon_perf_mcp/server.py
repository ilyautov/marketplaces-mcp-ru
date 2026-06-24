#!/usr/bin/env python3
"""ozon_perf_mcp — MCP server for the Ozon Performance (advertising) API.

Exposes the whole Ozon Performance API through the same schema-driven meta-tools
(search / describe / call / fetch_all) used by the other servers. Single host
(api-performance.ozon.ru). Credentials are SEPARATE from the Ozon Seller API.

Auth: OAuth2 client_credentials.
    POST https://api-performance.ozon.ru/api/client/token
         {"client_id": ..., "client_secret": ..., "grant_type": "client_credentials"}
      -> 200 {"access_token": "...", "expires_in": 1800, "token_type": "Bearer"}
    Every subsequent request sends: Authorization: Bearer <access_token>

The token fetch/cache/refresh lives entirely in core.client.MarketplaceClient and
is enabled purely by setting `token_url` on the ServiceConfig below.

!!! UNVERIFIED CONTRACT !!!
The token contract above is taken from Ozon's documentation but has NOT been
exercised against the live API (no Performance credentials were available when
this server was written). If live calls fail at the token step, the single place
to adjust is MarketplaceClient._fetch_token in core/client.py (field names, JSON
vs form-encoding, token_type handling).

Run:
    OZON_PERF_CLIENT_ID=... OZON_PERF_CLIENT_SECRET=... python -m ozon_perf_mcp.server
"""
from __future__ import annotations

import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from core.client import MarketplaceClient, ServiceConfig
from core.registry import Catalog
from core.tools import register_cabinet_tools, register_generic_tools
from core.workflows import Workflows, register_workflow_tools

# The perf catalog lives next to the Ozon Seller catalog (already prepared:
# 45 endpoints, host api-performance.ozon.ru, default_host set).
CATALOG_PATH = Path(__file__).resolve().parent.parent / "ozon_mcp" / "perf_endpoints.yaml"
WORKFLOWS_PATH = Path(__file__).with_name("workflows.yaml")


def _build_headers(creds: dict[str, str]) -> dict[str, str]:
    """Non-auth default headers. Auth is handled by the OAuth bearer flow in
    MarketplaceClient (token_url set below), so this only sets Content-Type."""
    return {"Content-Type": "application/json"}


OZON_PERF_CONFIG = ServiceConfig(
    name="ozon_perf",
    scheme="https",
    fields=["client_id", "client_secret"],
    env_map={
        "client_id": "OZON_PERF_CLIENT_ID",
        "client_secret": "OZON_PERF_CLIENT_SECRET",
    },
    build_headers=_build_headers,
    # Enabling OAuth2 client_credentials. UNVERIFIED live (see module docstring).
    token_url="https://api-performance.ozon.ru/api/client/token",
    oauth_id_field="client_id",
    oauth_secret_field="client_secret",
)

mcp = FastMCP("ozon_perf_mcp")
catalog = Catalog.from_yaml(CATALOG_PATH)
client = MarketplaceClient(OZON_PERF_CONFIG)

register_generic_tools(
    mcp, svc="ozon_perf", client=client, catalog=catalog,
    key_help=("seller.ozon.ru → Performance API → API keys "
              "(Client-Id + Client-Secret; SEPARATE from Seller API keys)."),
)
register_cabinet_tools(mcp, svc="ozon_perf", client=client, catalog=catalog)
register_workflow_tools(
    mcp, svc="ozon_perf", workflows=Workflows.from_yaml(WORKFLOWS_PATH))


def _j(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, default=str)


def main() -> None:
    """Console entry point (stdio transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
