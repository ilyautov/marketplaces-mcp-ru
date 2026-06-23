#!/usr/bin/env python3
"""Self-bootstrapping launcher for the marketplace MCP servers.

Goal: zero manual setup. Point any MCP client at THIS file. On first run it
quietly creates a local virtual environment, installs dependencies, and re-execs
itself inside that venv. Subsequent runs start instantly.

    python3 serve.py wb      # launch the Wildberries server
    python3 serve.py ozon    # launch the Ozon server

All bootstrap chatter goes to STDERR only — STDOUT stays clean so the MCP stdio
handshake is never corrupted.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
VENV = HERE / ".venv"
DEPS = ["mcp>=1.2.0", "httpx>=0.27", "pyyaml>=6.0"]
SERVICES = {"wb": "wb_mcp.server", "ozon": "ozon_mcp.server"}
_FLAG = "MARKETPLACE_MCP_BOOTSTRAPPED"


def _log(msg: str) -> None:
    print(f"[marketplace-mcp] {msg}", file=sys.stderr, flush=True)


def _venv_python() -> Path:
    if os.name == "nt":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def _deps_importable() -> bool:
    try:
        import httpx  # noqa: F401
        import mcp  # noqa: F401
        import yaml  # noqa: F401
        return True
    except ImportError:
        return False


def _bootstrap_and_reexec(service: str) -> None:
    """Create venv, install deps, then re-exec inside the venv."""
    vpy = _venv_python()
    if not vpy.exists():
        _log(f"first run — creating virtual environment at {VENV} …")
        import venv
        venv.EnvBuilder(with_pip=True).create(VENV)
    _log("installing dependencies (one-time) …")
    subprocess.run(
        [str(vpy), "-m", "pip", "install", "--quiet", "--upgrade", "pip", *DEPS],
        check=True, stdout=sys.stderr.fileno(), stderr=sys.stderr.fileno(),
    )
    _log("ready — starting server.")
    env = dict(os.environ, **{_FLAG: "1"})
    os.execve(str(vpy), [str(vpy), str(Path(__file__).resolve()), service], env)


def main() -> None:
    if sys.version_info < (3, 10):
        _log(f"Python 3.10+ required, found {sys.version.split()[0]}. "
             "Install a newer Python from https://python.org and retry.")
        sys.exit(1)
    if len(sys.argv) < 2 or sys.argv[1] not in SERVICES:
        _log(f"usage: python3 serve.py [{'|'.join(SERVICES)}]")
        sys.exit(2)
    service = sys.argv[1]

    # Make `core`, `wb_mcp`, `ozon_mcp` importable regardless of cwd.
    sys.path.insert(0, str(HERE))

    if not _deps_importable():
        if os.environ.get(_FLAG):
            # Already re-exec'd once but deps still missing — surface clearly.
            _log("dependencies still unavailable after bootstrap. Install manually: "
                 f"pip install {' '.join(DEPS)}")
            sys.exit(1)
        _bootstrap_and_reexec(service)
        return  # not reached (execve replaces process)

    module = SERVICES[service]
    import importlib
    server = importlib.import_module(module)
    server.main()


if __name__ == "__main__":
    main()
