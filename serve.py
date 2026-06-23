#!/usr/bin/env python3
"""Self-bootstrapping launcher for the marketplace MCP servers.

Goal: zero manual setup, identical on Windows, macOS and Linux. Point any MCP
client at THIS file. On first run it quietly creates a local virtual environment,
installs dependencies, and injects them into the current process — then runs the
server. Subsequent runs start instantly.

    python3 serve.py wb            # launch the Wildberries server
    python3 serve.py ozon          # launch the Ozon server
    python3 serve.py ozon --selfcheck   # verify install, print tool count, exit

Why no process re-exec: an MCP stdio server must stay in the SAME process that
owns stdin/stdout. Swapping the process (os.exec*) is fragile on Windows and can
break the stdio handshake, so instead we install into a venv and add that venv's
site-packages to sys.path of the running interpreter. The venv is created by the
current interpreter, so its packages are ABI-compatible.

All bootstrap chatter goes to STDERR only — STDOUT stays clean.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
VENV = Path(os.environ.get("MARKETPLACE_MCP_VENV", HERE / ".venv"))
DEPS = ["mcp>=1.2.0", "httpx>=0.27", "pyyaml>=6.0"]
SERVICES = {"wb": "wb_mcp.server", "ozon": "ozon_mcp.server",
            "ozon-perf": "ozon_perf_mcp.server"}


def _log(msg: str) -> None:
    print(f"[marketplace-mcp] {msg}", file=sys.stderr, flush=True)


def _venv_python() -> Path:
    return VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _venv_site_packages() -> list[Path]:
    if os.name == "nt":
        return [VENV / "Lib" / "site-packages"]
    return list(VENV.glob("lib/python*/site-packages"))


def _deps_importable() -> bool:
    try:
        import httpx  # noqa: F401
        import mcp  # noqa: F401
        import yaml  # noqa: F401
        return True
    except ImportError:
        return False


def _ensure_deps() -> bool:
    """Make mcp/httpx/yaml importable in THIS process. Returns success."""
    if _deps_importable():
        return True
    vpy = _venv_python()
    if not vpy.exists():
        _log(f"first run — creating virtual environment at {VENV} …")
        import venv
        venv.EnvBuilder(with_pip=True).create(VENV)
    _log("installing dependencies (one-time) …")
    try:
        subprocess.run(
            [str(vpy), "-m", "pip", "install", "--quiet", "--upgrade", "pip", *DEPS],
            check=True, stdout=sys.stderr.fileno(), stderr=sys.stderr.fileno(),
        )
    except (subprocess.CalledProcessError, OSError) as exc:
        _log(f"dependency install failed: {exc}")
        return False
    # inject the venv's site-packages into the running interpreter
    for sp in _venv_site_packages():
        if sp.is_dir():
            sys.path.insert(0, str(sp))
    return _deps_importable()


def main() -> None:
    if sys.version_info < (3, 10):
        _log(f"Python 3.10+ required, found {sys.version.split()[0]}. "
             "Install a newer Python from https://python.org and retry.")
        sys.exit(1)
    args = [a for a in sys.argv[1:]]
    selfcheck = "--selfcheck" in args
    positional = [a for a in args if not a.startswith("-")]
    if not positional or positional[0] not in SERVICES:
        _log(f"usage: python serve.py [{'|'.join(SERVICES)}] [--selfcheck]")
        sys.exit(2)
    service = positional[0]

    sys.path.insert(0, str(HERE))  # make core/, wb_mcp/, ozon_mcp/ importable

    if not _ensure_deps():
        _log(f"dependencies unavailable. Install manually: pip install {' '.join(DEPS)}")
        sys.exit(1)

    import importlib
    server = importlib.import_module(SERVICES[service])

    if selfcheck:
        import asyncio
        tools = asyncio.run(server.mcp.list_tools())
        _log(f"selfcheck OK — {service} server exposes {len(tools)} tools.")
        print(f"OK: {service} ready, {len(tools)} tools.")
        return

    server.main()


if __name__ == "__main__":
    main()
