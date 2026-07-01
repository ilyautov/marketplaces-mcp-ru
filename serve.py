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
# Upper bounds on purpose: a future mcp 2.x / httpx 1.x must not silently
# break existing installs on their next automatic dependency refresh.
DEPS = ["mcp>=1.2,<2", "httpx>=0.27,<1", "pyyaml>=6.0,<7"]
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


def _deps_stamp() -> Path:
    """Version stamp of the installed dependency set (lives inside the venv)."""
    return VENV / "deps-stamp.txt"


def _stamp_current() -> bool:
    try:
        return _deps_stamp().read_text(encoding="utf-8").strip() == "\n".join(DEPS)
    except OSError:
        return False


def _write_stamp() -> None:
    try:
        _deps_stamp().write_text("\n".join(DEPS), encoding="utf-8")
    except OSError:
        pass  # non-fatal: next start just re-checks via pip


def _inject_site_packages() -> None:
    """Put the venv's site-packages onto sys.path of THIS interpreter."""
    for sp in _venv_site_packages():
        if sp.is_dir() and str(sp) not in sys.path:
            sys.path.insert(0, str(sp))


def _pip_install() -> bool:
    try:
        subprocess.run(
            [str(_venv_python()), "-m", "pip", "install", "--quiet", *DEPS],
            check=True, stdout=sys.stderr.fileno(), stderr=sys.stderr.fileno(),
        )
        return True
    except (subprocess.CalledProcessError, OSError) as exc:
        _log(f"dependency install failed: {exc}")
        return False


def _ensure_deps() -> bool:
    """Make mcp/httpx/yaml importable in THIS process. Returns success.

    Fast path first: inject the venv's site-packages and try importing — a
    machine with a provisioned venv starts instantly and fully OFFLINE (no
    pip, no network). pip only runs when deps are missing or the pinned DEPS
    set changed (detected via the deps-stamp file inside the venv)."""
    _inject_site_packages()
    if _deps_importable() and (not _venv_python().exists() or _stamp_current()):
        return True  # ready venv (or system-wide deps) — no pip, works offline

    import venv
    if not _venv_python().exists():
        _log(f"first run — creating virtual environment at {VENV} …")
        venv.EnvBuilder(with_pip=True).create(VENV)
        _log("installing dependencies (one-time) …")
    else:
        _log("refreshing dependencies …")

    if _pip_install():
        _inject_site_packages()
        if _deps_importable():
            _write_stamp()
            return True
    elif _deps_importable():
        # Offline but the previously installed deps import fine — run with
        # them and retry the refresh on a later start.
        _log("could not refresh dependencies (offline?) — using installed ones.")
        return True

    # Install didn't help — the venv likely belongs to another Python
    # version. Recreate it once and try again.
    _log(f"recreating virtual environment at {VENV} …")
    venv.EnvBuilder(with_pip=True, clear=True).create(VENV)
    if not _pip_install():
        return False
    _inject_site_packages()
    if _deps_importable():
        _write_stamp()
        return True
    return False


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
