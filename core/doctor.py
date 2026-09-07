"""``doctor`` — one command that says whether this install can actually work.

For each service (Wildberries, Ozon Seller, Ozon Performance) it reports:

* how many MCP tools are mounted and how many catalog methods loaded,
* whether credentials were found and where (cabinet name, ``env`` or none),
* with ``--live``: one cheap real read call (the service's *whoami* endpoint),
  which proves the marketplace accepts the key, not merely that it is present.

Never prints a secret. Exit code 0 when every service that has credentials
passed; 1 when no service has credentials at all, a catalog failed to load, or
a live probe failed.

    python3 serve.py doctor [--live] [--json]
    marketplaces-mcp-ru doctor [--live] [--json]
    docker run --rm -e WB_API_TOKEN=... ghcr.io/ilyautov/marketplaces-mcp-ru doctor --live
"""
from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import sys
from dataclasses import asdict, dataclass, field
from typing import Any, Optional, Sequence

SERVICES: tuple[tuple[str, str, str], ...] = (
    ("wb", "Wildberries", "wb_mcp.server"),
    ("ozon", "Ozon Seller", "ozon_mcp.server"),
    ("ozon_perf", "Ozon Performance", "ozon_perf_mcp.server"),
    ("ym", "Yandex Market", "yandex_mcp.server"),
    ("avito", "Avito", "avito_mcp.server"),
)


@dataclass
class ServiceReport:
    service: str
    title: str
    tools: int = 0
    methods: int = 0
    ready: bool = False
    source: str = "none"            # cabinet name, "env" or "none"
    active_cabinet: Optional[str] = None
    missing: list[str] = field(default_factory=list)
    env_names: list[str] = field(default_factory=list)
    live: Optional[str] = None      # "ok" | "fail" | "skipped"; None = not requested
    live_detail: str = ""
    error: str = ""                 # import / catalog failure


def _tool_text(result: Any) -> str:
    """Flatten ``FastMCP.call_tool`` output down to the tool's text payload."""
    if isinstance(result, dict):
        return json.dumps(result)
    if isinstance(result, tuple):  # (content, structured) in some SDK versions
        result = result[0]
    for block in result:
        text = getattr(block, "text", None)
        if text is not None:
            return text
    return ""


async def _probe(mod: Any) -> tuple[str, str]:
    """One real read call. Returns (status, detail)."""
    whoami = getattr(mod.client.config, "whoami", None)
    if not whoami:
        return "skipped", "no whoami endpoint for this service"
    spec = mod.catalog.get(whoami[0])
    if spec is None:
        return "skipped", f"{whoami[0]} is not in the catalog"
    try:
        r = await mod.client.call_spec(spec)
    except Exception as exc:  # noqa: BLE001 — report, never crash the doctor
        return "fail", f"{type(exc).__name__}: {exc}"
    if r.get("ok"):
        return "ok", f"HTTP {r.get('status')} {spec.method} {spec.path}"
    return "fail", f"{r.get('error')}: {str(r.get('message', ''))[:160]}"


async def inspect_service(svc: str, title: str, module_name: str, live: bool) -> ServiceReport:
    rep = ServiceReport(service=svc, title=title)
    try:
        mod = importlib.import_module(module_name)
        rep.tools = len(await mod.mcp.list_tools())
        rep.methods = len(mod.catalog.all())
        cfg = mod.client.config
        rep.env_names = [cfg.env_map[f] for f in cfg.fields]
        auth = json.loads(_tool_text(await mod.mcp.call_tool(f"{svc}_check_auth", {})))
    except Exception as exc:  # noqa: BLE001
        rep.error = f"{type(exc).__name__}: {exc}"
        return rep
    rep.ready = bool(auth.get("ready"))
    rep.source = str(auth.get("source") or "none")
    rep.active_cabinet = auth.get("active_cabinet")
    rep.missing = list(auth.get("missing_fields") or [])
    if live and rep.ready:
        rep.live, rep.live_detail = await _probe(mod)
    return rep


async def run_all(live: bool) -> list[ServiceReport]:
    # Sequential on purpose: each module builds its FastMCP as an import side
    # effect, and the shared credential store is read-only here anyway.
    return [await inspect_service(svc, title, mod, live) for svc, title, mod in SERVICES]


def exit_code(reports: Sequence[ServiceReport], live: bool) -> int:
    if any(r.error for r in reports):
        return 1
    ready = [r for r in reports if r.ready]
    if not ready:
        return 1
    if live and any(r.live == "fail" for r in ready):
        return 1
    return 0


def _creds_cell(r: ServiceReport) -> str:
    if r.error:
        return "ERROR (see below)"
    if r.ready:
        if r.source == "env":
            return "env"
        return f'cabinet "{r.source}"'
    return "none — set " + ", ".join(r.env_names or r.missing)


def format_table(reports: Sequence[ServiceReport], live: bool) -> str:
    lines = ["marketplaces-mcp-ru doctor", ""]
    width = max(34, *(len(_creds_cell(r)) for r in reports)) if reports else 34
    head = f"{'service':<18}{'tools':>6}{'methods':>9}  {'credentials':<{width}}"
    if live:
        head += "  live"
    lines.append(head.rstrip())
    lines.append("-" * len(head.rstrip()))
    for r in reports:
        row = f"{r.title:<18}{r.tools:>6}{r.methods:>9}  {_creds_cell(r):<{width}}"
        if live:
            if r.live is None:
                row += "  -"
            else:
                row += "  " + (f"{r.live} ({r.live_detail})" if r.live_detail else r.live)
        lines.append(row.rstrip())
    lines.append("")
    for r in reports:
        if r.error:
            lines.append(f"! {r.title}: {r.error}")
    if not any(r.ready for r in reports):
        lines.append("No credentials found for any marketplace. Run install.py, "
                     "or say «добавь кабинет» in chat (*_add_cabinet). "
                     "Nothing is broken — the servers just have nowhere to log in.")
    elif live and any(r.live == "fail" for r in reports):
        lines.append("A live probe failed: the key is present but the marketplace "
                     "rejected it (revoked, wrong scopes, or a network issue).")
    else:
        lines.append("OK." if not live else "OK — configured marketplaces answered.")
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="marketplaces-mcp-ru doctor",
        description="Check tools, catalogs and credentials for every marketplace server.",
    )
    parser.add_argument("--live", action="store_true",
                        help="also make one real read call per configured marketplace")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(list(argv) if argv is not None else None)

    reports = asyncio.run(run_all(args.live))
    if args.json:
        print(json.dumps([asdict(r) for r in reports], ensure_ascii=False, indent=2))
    else:
        print(format_table(reports, args.live))
    return exit_code(reports, args.live)


if __name__ == "__main__":
    sys.exit(main())
