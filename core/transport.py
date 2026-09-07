"""Transport selection shared by every entry point.

stdio is the default and what every desktop client (Claude Desktop, Cursor,
Codex, Claude Code) speaks. Streamable HTTP is opt-in for containers and
remote hosts:

    MCP_TRANSPORT=stdio            default
    MCP_TRANSPORT=http             Streamable HTTP at http://HOST:PORT/mcp
    MCP_HTTP_HOST=127.0.0.1        bind address (use 0.0.0.0 inside Docker)
    MCP_HTTP_PORT=8000
    MCP_HTTP_ALLOWED_HOSTS=        comma-separated ``Host`` header allowlist
                                   (DNS-rebinding guard; ``myhost:*`` wildcards ok)

HTTP mode carries NO authentication of its own: whoever reaches the port can
call every tool with the cabinet keys this process holds. Keep it on
localhost, or put it behind a reverse proxy that authenticates. That is why
stdio stays the default and HTTP must be asked for explicitly.
"""
from __future__ import annotations

import os
import sys
from typing import Any, Mapping, Optional

STDIO = "stdio"
HTTP = "http"
_HTTP_ALIASES = {"http", "streamable-http", "streamable_http", "streamablehttp"}
_LOOPBACK = {"127.0.0.1", "localhost", "::1"}


def transport_from_env(env: Optional[Mapping[str, str]] = None) -> str:
    """Return ``"stdio"`` or ``"http"`` from ``MCP_TRANSPORT`` (default stdio)."""
    env = os.environ if env is None else env
    raw = (env.get("MCP_TRANSPORT") or STDIO).strip().lower()
    if raw == STDIO:
        return STDIO
    if raw in _HTTP_ALIASES:
        return HTTP
    raise ValueError(
        f"MCP_TRANSPORT={raw!r} is not supported; use 'stdio' (default) or 'http'"
    )


def configure_http(mcp: Any, env: Optional[Mapping[str, str]] = None) -> None:
    """Apply MCP_HTTP_* settings to a FastMCP instance before ``run``."""
    env = os.environ if env is None else env
    host = (env.get("MCP_HTTP_HOST") or mcp.settings.host).strip()
    port_raw = (env.get("MCP_HTTP_PORT") or "").strip()
    port = int(port_raw) if port_raw else int(mcp.settings.port)
    if not (0 < port < 65536):
        raise ValueError(f"MCP_HTTP_PORT={port} is out of range")
    mcp.settings.host = host
    mcp.settings.port = port

    allowed = [h.strip() for h in (env.get("MCP_HTTP_ALLOWED_HOSTS") or "").split(",")
               if h.strip()]
    if allowed:
        from mcp.server.transport_security import TransportSecuritySettings

        mcp.settings.transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=True, allowed_hosts=allowed,
        )
    elif host not in _LOOPBACK:
        # FastMCP pre-builds a localhost-only Host allowlist when constructed
        # with its default 127.0.0.1. Rebinding to another interface with that
        # allowlist still in place would reject every real request (421). Match
        # the SDK's own behaviour for non-loopback hosts: no allowlist unless
        # the operator names one.
        mcp.settings.transport_security = None
        print(
            f"[marketplaces-mcp-ru] HTTP bound to {host}:{port} without "
            "MCP_HTTP_ALLOWED_HOSTS — no auth of its own; keep it behind a "
            "proxy or firewall.",
            file=sys.stderr, flush=True,
        )


def run(mcp: Any, env: Optional[Mapping[str, str]] = None) -> None:
    """Run ``mcp`` on the transport the environment asks for."""
    if transport_from_env(env) == STDIO:
        mcp.run()
        return
    configure_http(mcp, env)
    mcp.run(transport="streamable-http")
