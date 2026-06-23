#!/usr/bin/env python3
"""End-to-end smoke test over the real MCP stdio protocol.

Launches each server exactly as an MCP client (Cowork, Claude Desktop) would —
as a subprocess speaking stdio — then initializes a session, lists tools, and
calls a read-only tool. This verifies the client actually sees and can invoke
the tools, which direct in-process calls do not prove.

Run:  python3 scripts/smoke_mcp.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent.parent


async def probe(service: str) -> bool:
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(ROOT / "serve.py"), service],
        cwd=str(ROOT),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = (await session.list_tools()).tools
            names = sorted(t.name for t in tools)
            print(f"[{service}] tools visible to client: {len(names)}")
            print(f"  {', '.join(names)}")
            # call a read-only tool that needs no creds
            res = await session.call_tool(f"{service}_list_sections", {})
            text = res.content[0].text if res.content else ""
            ok = '"total_endpoints"' in text or "sections" in text
            print(f"[{service}] {service}_list_sections via protocol: "
                  f"{'OK' if ok else 'UNEXPECTED'} ({len(text)} bytes)")
            # check_auth should report missing creds gracefully (no crash)
            res2 = await session.call_tool(f"{service}_check_auth", {})
            t2 = res2.content[0].text if res2.content else ""
            print(f"[{service}] {service}_check_auth: "
                  f"{'OK' if 'ready' in t2 else 'UNEXPECTED'}")
            return ok and len(names) >= 13


async def main() -> None:
    results = []
    for svc in ("wb", "ozon"):
        try:
            results.append(await probe(svc))
        except Exception as exc:  # noqa: BLE001
            print(f"[{svc}] FAILED: {type(exc).__name__}: {exc}")
            results.append(False)
    print("\nRESULT:", "ALL PASS" if all(results) else "SOME FAILED")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    asyncio.run(main())
