"""Combined MCP server: Wildberries + Ozon + Ozon-Perf on one FastMCP.

One process, one stdio channel, every tool. This backs both the `.mcpb`
Claude Desktop bundle (`serve.py all`) and the `marketplaces-mcp-ru` console
script (`uvx marketplaces-mcp-ru`).

Tool names are already namespaced per service (``wb_*`` / ``ozon_*`` /
``ozon_perf_*``), so merging the three servers' tool sets can never collide.
Each service module builds its FastMCP as an import side effect; we copy the
already-registered tools onto a single parent via FastMCP's tool manager. That
internal surface is stable within the pinned ``mcp>=1.2,<2`` range.
"""
from __future__ import annotations

import importlib
import sys
from typing import Optional, Sequence

from mcp.server.fastmcp import FastMCP

from core.transport import run as run_transport

SERVICE_MODULES = ("wb_mcp.server", "ozon_mcp.server", "ozon_perf_mcp.server")


def build() -> FastMCP:
    """Return one FastMCP carrying every service's tools."""
    combined = FastMCP("marketplaces-mcp-ru")
    for mod_name in SERVICE_MODULES:
        mod = importlib.import_module(mod_name)
        combined._tool_manager._tools.update(mod.mcp._tool_manager._tools)
    return combined


def main(argv: Optional[Sequence[str]] = None) -> None:
    """Console entry point.

    ``marketplaces-mcp-ru``          serve (stdio; HTTP with MCP_TRANSPORT=http)
    ``marketplaces-mcp-ru doctor``   diagnostics, see ``core.doctor``
    """
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "doctor":
        from core.doctor import main as doctor_main

        raise SystemExit(doctor_main(args[1:]))
    if args:
        print(f"marketplaces-mcp-ru: unknown argument {args[0]!r} "
              "(only 'doctor' is accepted)", file=sys.stderr)
        raise SystemExit(2)
    run_transport(build())


if __name__ == "__main__":
    main()
