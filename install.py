#!/usr/bin/env python3
"""One-command installer: wires both marketplace servers into Claude / Cowork.

It locates your Claude desktop config, asks for API keys (or takes them as
flags), writes the two MCP server entries pointing at serve.py, and backs up the
old config. No manual JSON editing, no pip install — serve.py self-bootstraps on
first launch.

    python3 install.py                 # interactive (asks for keys)
    python3 install.py --print         # just print the JSON block, change nothing
    python3 install.py --wb-token T --ozon-client-id ID --ozon-api-key KEY

Re-running is safe: it updates the two entries and leaves everything else alone.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
SERVE = HERE / "serve.py"


def config_path() -> Path:
    """Best-effort Claude desktop config path for this OS."""
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    if sys.platform.startswith("win"):
        import os
        base = Path(os.environ.get("APPDATA", home))
        return base / "Claude" / "claude_desktop_config.json"
    return home / ".config" / "Claude" / "claude_desktop_config.json"


def build_entries(wb_token: str, ozon_client_id: str, ozon_api_key: str) -> dict:
    py = sys.executable  # the interpreter that ran install.py
    return {
        "wildberries": {
            "command": py,
            "args": [str(SERVE), "wb"],
            "env": {"WB_API_TOKEN": wb_token},
        },
        "ozon": {
            "command": py,
            "args": [str(SERVE), "ozon"],
            "env": {"OZON_CLIENT_ID": ozon_client_id, "OZON_API_KEY": ozon_api_key},
        },
    }


def _ask(prompt: str, current: str) -> str:
    if current:
        return current
    try:
        return input(prompt).strip()
    except EOFError:
        return ""


def claude_code_commands(wb_token: str, ozon_client_id: str, ozon_api_key: str) -> str:
    """Equivalent `claude mcp add` commands for Claude Code (CLI) users."""
    py = sys.executable
    return (
        f'claude mcp add wildberries --env WB_API_TOKEN={wb_token or "YOUR_WB_TOKEN"} '
        f'-- "{py}" "{SERVE}" wb\n'
        f'claude mcp add ozon --env OZON_CLIENT_ID={ozon_client_id or "YOUR_ID"} '
        f'--env OZON_API_KEY={ozon_api_key or "YOUR_KEY"} -- "{py}" "{SERVE}" ozon'
    )


def main() -> None:
    if sys.version_info < (3, 10):
        sys.exit(f"Python 3.10+ required, found {sys.version.split()[0]}. "
                 "Install from https://python.org and retry.")
    ap = argparse.ArgumentParser()
    ap.add_argument("--wb-token", default="")
    ap.add_argument("--ozon-client-id", default="")
    ap.add_argument("--ozon-api-key", default="")
    ap.add_argument("--print", action="store_true", dest="print_only",
                    help="print the config block and exit (change nothing)")
    ap.add_argument("--claude-code", action="store_true",
                    help="print `claude mcp add` commands for Claude Code instead")
    ap.add_argument("--config", default="", help="override config file path")
    args = ap.parse_args()

    if args.claude_code:
        print(claude_code_commands(args.wb_token, args.ozon_client_id, args.ozon_api_key))
        return

    if not args.print_only:
        print("Marketplace MCP installer — keys are stored in your local Claude "
              "config only.\n"
              "Get WB token: seller.wildberries.ru → Settings → Access tokens.\n"
              "Get Ozon keys: seller.ozon.ru → Settings → API keys.\n")
    wb = _ask("Wildberries API token (Enter to skip): ", args.wb_token) if not args.print_only else args.wb_token
    oid = _ask("Ozon Client-Id (Enter to skip): ", args.ozon_client_id) if not args.print_only else args.ozon_client_id
    okey = _ask("Ozon Api-Key (Enter to skip): ", args.ozon_api_key) if not args.print_only else args.ozon_api_key

    entries = build_entries(wb, oid, okey)

    if args.print_only:
        print(json.dumps({"mcpServers": entries}, ensure_ascii=False, indent=2))
        return

    cfg_path = Path(args.config) if args.config else config_path()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)

    config: dict = {}
    if cfg_path.exists():
        try:
            config = json.loads(cfg_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"⚠️  {cfg_path} is not valid JSON; starting fresh (old file backed up).")
        backup = cfg_path.with_suffix(f".json.bak-{datetime.now():%Y%m%d-%H%M%S}")
        shutil.copy2(cfg_path, backup)
        print(f"Backed up existing config → {backup.name}")

    config.setdefault("mcpServers", {})
    config["mcpServers"].update(entries)
    cfg_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n✅ Wrote config → {cfg_path}")
    print("   Servers added: 'wildberries', 'ozon'.")
    missing = [n for n, v in {"WB_API_TOKEN": wb, "OZON_CLIENT_ID": oid,
                              "OZON_API_KEY": okey}.items() if not v]
    if missing:
        print(f"   ⚠️  Empty keys: {', '.join(missing)} — edit the config later or "
              "re-run install.py.")
    print("\n👉 Restart Claude / Cowork. First launch auto-installs dependencies "
          "(a few seconds), then the tools appear.")
    print("\n(Using Claude Code CLI instead? Run `python3 install.py --claude-code` "
          "for the equivalent `claude mcp add` commands.)")


if __name__ == "__main__":
    main()
