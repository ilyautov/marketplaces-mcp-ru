#!/usr/bin/env python3
"""One-command installer: wires both marketplace servers into Claude / Cowork.

Blessed path: drop the repo into Cowork and say "install WB+Ozon MCP". The
installer copies the app to a canonical, stable location (~/.marketplace-mcp/app)
and points the client config THERE — so when the mounted/cloned folder later
moves or unmounts, the MCP keeps working. It then asks for API keys (or takes
them as flags), backs up the old config, and writes secret-free server entries.
No manual JSON editing, no pip install — serve.py self-bootstraps deps on first
launch.

    python3 install.py                 # interactive (asks for keys), copies to canonical dir
    python3 install.py --with-ads      # also ask Ozon Performance (ads) keys
    python3 install.py --in-place      # do NOT copy; run from this folder (manual/dev)
    python3 install.py --print         # just print the JSON block, change nothing
    python3 install.py --wb-token T --ozon-client-id ID --ozon-api-key KEY

Re-running is safe: it refreshes the app copy and the two entries, leaving
everything else alone.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Canonical, stable home — decoupled from where the repo was dropped/cloned.
# Overridable for tests via MARKETPLACE_MCP_HOME.
APP_HOME = Path(os.environ.get("MARKETPLACE_MCP_HOME", Path.home() / ".marketplace-mcp"))
APP_DIR = APP_HOME / "app"
# Everything serve.py needs at runtime (packages carry their own *.yaml).
RUNTIME_ITEMS = ["core", "wb_mcp", "ozon_mcp", "ozon_perf_mcp", "serve.py", "pyproject.toml"]
# SERVE points at the canonical copy once installed; reassigned in main().
SERVE = APP_DIR / "serve.py"
sys.path.insert(0, str(HERE))
from core.credentials import CredentialStore  # noqa: E402


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


def build_entries() -> dict:
    """Server entries for the Claude config. No secrets here — credentials live
    in the cabinet store (~/.marketplace-mcp/cabinets.json)."""
    py = sys.executable  # the interpreter that ran install.py
    return {
        "wildberries": {"command": py, "args": [str(SERVE), "wb"]},
        "ozon": {"command": py, "args": [str(SERVE), "ozon"]},
        # Ozon Performance (advertising) API — OAuth2, separate perf credentials.
        "ozon-perf": {"command": py, "args": [str(SERVE), "ozon-perf"]},
    }


def save_cabinet(cabinet: str, wb_token: str, oid: str, okey: str,
                 perf_id: str = "", perf_secret: str = "") -> None:
    """Persist provided keys as a named cabinet in the local store.

    Ozon Performance (advertising) creds are SEPARATE from the Seller API keys
    and entirely optional — only saved if both are provided."""
    store = CredentialStore()
    if wb_token:
        store.add_cabinet("wb", cabinet, {"token": wb_token}, make_active=True)
    if oid and okey:
        store.add_cabinet("ozon", cabinet,
                          {"client_id": oid, "api_key": okey}, make_active=True)
    if perf_id and perf_secret:
        store.add_cabinet("ozon_perf", cabinet,
                          {"client_id": perf_id, "client_secret": perf_secret},
                          make_active=True)


def _ask(prompt: str, current: str) -> str:
    if current:
        return current
    try:
        return input(prompt).strip()
    except EOFError:
        return ""


def claude_code_commands() -> str:
    """Equivalent `claude mcp add` commands for Claude Code (CLI) users.
    Credentials come from the cabinet store, so no --env secrets are needed."""
    py = sys.executable
    return (
        f'claude mcp add wildberries -- "{py}" "{SERVE}" wb\n'
        f'claude mcp add ozon -- "{py}" "{SERVE}" ozon\n'
        f'claude mcp add ozon-perf -- "{py}" "{SERVE}" ozon-perf\n'
        "# then add a cabinet from chat: ozon_add_cabinet / wb_add_cabinet, "
        "or re-run: python3 install.py"
    )


def codex_commands() -> str:
    """`codex mcp add` commands for OpenAI Codex CLI (config: ~/.codex/config.toml)."""
    py = sys.executable
    return (
        f'codex mcp add wildberries -- "{py}" "{SERVE}" wb\n'
        f'codex mcp add ozon -- "{py}" "{SERVE}" ozon\n'
        f'codex mcp add ozon-perf -- "{py}" "{SERVE}" ozon-perf\n'
        "# then add a cabinet: python3 install.py  (keys -> ~/.marketplace-mcp)"
    )


def opencode_config_path() -> Path:
    """Global OpenCode config (~/.config/opencode/opencode.json on every OS)."""
    return Path.home() / ".config" / "opencode" / "opencode.json"


def build_opencode_entries() -> dict:
    """OpenCode 'mcp' entries: type local + command array, secret-free."""
    py = sys.executable
    return {
        "wildberries": {"type": "local", "command": [py, str(SERVE), "wb"], "enabled": True},
        "ozon": {"type": "local", "command": [py, str(SERVE), "ozon"], "enabled": True},
        "ozon-perf": {"type": "local", "command": [py, str(SERVE), "ozon-perf"], "enabled": True},
    }


def install_app(src: Path, dest: Path) -> Path:
    """Copy the runtime app from `src` into the canonical `dest`, return the
    canonical serve.py. Skips if already running from `dest`. Never touches the
    source's .git — we only read out of it (safe even on a Cowork FUSE mount,
    where git operations fail). Returns dest/serve.py."""
    if src.resolve() == dest.resolve():
        return dest / "serve.py"          # already canonical — re-run in place
    dest.mkdir(parents=True, exist_ok=True)
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".venv", ".git")
    for item in RUNTIME_ITEMS:
        s = src / item
        if not s.exists():
            continue
        d = dest / item
        if s.is_dir():
            shutil.copytree(s, d, dirs_exist_ok=True, ignore=ignore)
        else:
            shutil.copy2(s, d)
    return dest / "serve.py"


def write_breadcrumb(config_path: Path, entries: dict, serve_path: Path,
                     source: Path) -> Path:
    """Write a visible, secret-free record of the install so it can be verified
    without reading the client's protected config dir (Cowork blocks that).
    Lands at ~/.marketplace-mcp/last_install.json."""
    APP_HOME.mkdir(parents=True, exist_ok=True)
    crumb = APP_HOME / "last_install.json"
    crumb.write_text(json.dumps({
        "installed_at": datetime.now().isoformat(timespec="seconds"),
        "servers": sorted(entries.keys()),
        "serve_py": str(serve_path),
        "installed_from": str(source),
        "client_config": str(config_path),
        "note": "Verify after restart via MCP tools (wb_check_auth), not by reading the config.",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return crumb


def main() -> None:
    if sys.version_info < (3, 10):
        sys.exit(f"Python 3.10+ required, found {sys.version.split()[0]}. "
                 "Install from https://python.org and retry.")
    ap = argparse.ArgumentParser()
    ap.add_argument("--cabinet", default="main",
                    help="name for this cabinet (default 'main'); use different "
                         "names for multiple shops")
    ap.add_argument("--wb-token", default="")
    ap.add_argument("--ozon-client-id", default="")
    ap.add_argument("--ozon-api-key", default="")
    ap.add_argument("--ozon-perf-client-id", default="",
                    help="Ozon Performance (ads) Client-Id — optional, OAuth2")
    ap.add_argument("--ozon-perf-client-secret", default="",
                    help="Ozon Performance (ads) Client-Secret — optional, OAuth2")
    ap.add_argument("--print", action="store_true", dest="print_only",
                    help="print the config block and exit (change nothing)")
    ap.add_argument("--claude-code", action="store_true",
                    help="print `claude mcp add` commands for Claude Code instead")
    ap.add_argument("--client", choices=["claude-desktop","claude-code","codex","opencode"],
                    default="", help="target client (default: claude-desktop). "
                    "codex/claude-code print CLI commands; opencode writes opencode.json")
    ap.add_argument("--config", default="", help="override config file path")
    ap.add_argument("--with-ads", action="store_true",
                    help="also prompt for Ozon Performance (ads) keys "
                         "(default: skip — keeps the interactive flow to 3 fields)")
    ap.add_argument("--in-place", action="store_true",
                    help="do NOT copy to the canonical dir; point the config at "
                         "this folder (manual/dev use — the folder must not move)")
    args = ap.parse_args()

    # Canonical install: copy the app to a stable home and point config there.
    # --print and --in-place keep the in-folder path (no copy).
    global SERVE
    if args.print_only or args.in_place:
        SERVE = HERE / "serve.py"
    else:
        SERVE = install_app(HERE, APP_DIR)
        print(f"✅ App installed to {APP_DIR}\n"
              "   (stable location — you can move or delete the source folder now.)\n")

    client = args.client or ("claude-code" if args.claude_code else "claude-desktop")
    if client == "claude-code":
        print(claude_code_commands()); return
    if client == "codex":
        print(codex_commands()); return

    entries = build_entries()
    if args.print_only:
        print(json.dumps({"mcpServers": entries}, ensure_ascii=False, indent=2))
        return

    print("Marketplace MCP installer.\n"
          f"Cabinet name: '{args.cabinet}' (run again with --cabinet NAME to add "
          "more shops).\n"
          "Keys are saved to ~/.marketplace-mcp/cabinets.json (local, chmod 600), "
          "never to the repo.\n"
          "Get WB token: seller.wildberries.ru → Settings → Access tokens.\n"
          "Get Ozon keys: seller.ozon.ru → Settings → API keys.\n")
    wb = _ask("Wildberries API token (Enter to skip): ", args.wb_token)
    oid = _ask("Ozon Client-Id (Enter to skip): ", args.ozon_client_id)
    okey = _ask("Ozon Api-Key (Enter to skip): ", args.ozon_api_key)
    # Performance (ads) API — optional, separate OAuth2 credentials. Hidden by
    # default so a non-technical seller answers 3 fields, not 5; surfaced with
    # --with-ads (or implicitly when perf keys are passed as flags).
    with_ads = args.with_ads or bool(args.ozon_perf_client_id or args.ozon_perf_client_secret)
    if with_ads:
        perf_id = _ask("Ozon Performance Client-Id (Enter to skip): ",
                       args.ozon_perf_client_id)
        perf_secret = _ask("Ozon Performance Client-Secret (Enter to skip): ",
                           args.ozon_perf_client_secret)
    else:
        perf_id, perf_secret = args.ozon_perf_client_id, args.ozon_perf_client_secret

    # 1) save credentials to the cabinet store
    save_cabinet(args.cabinet, wb, oid, okey, perf_id, perf_secret)

    # 2) write the (secret-free) server entries to the target client config
    if client == "opencode":
        cfg_path = opencode_config_path(); cfg_key = "mcp"; entries = build_opencode_entries()
    else:  # claude-desktop
        cfg_path = Path(args.config) if args.config else config_path(); cfg_key = "mcpServers"
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
    config.setdefault(cfg_key, {})
    config[cfg_key].update(entries)
    cfg_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n✅ Config → {cfg_path} ({client}: servers 'wildberries', 'ozon', no secrets in it)")
    crumb = write_breadcrumb(cfg_path, entries, SERVE, HERE)
    print(f"✅ Install record → {crumb} (verify after restart, no secrets)")
    saved = [s for s, v in (("WB", wb), ("Ozon", oid and okey),
                            ("Ozon-Perf", perf_id and perf_secret)) if v]
    print(f"✅ Cabinet '{args.cabinet}' saved for: {', '.join(saved) or '(nothing — keys skipped)'}")
    print("\n👉 Restart Claude / Cowork. First launch auto-installs dependencies, "
          "then the tools appear.")
    print("   Add another shop later: re-run with --cabinet shop2, or in chat say "
          "'add an Ozon cabinet' (ozon_add_cabinet). Switch with ozon_use_cabinet.")


if __name__ == "__main__":
    main()
