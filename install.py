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
from glob import glob
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


CLAUDE_CONFIG_NAME = "claude_desktop_config.json"


def _windows_claude_dirs() -> list[Path]:
    """Existing Claude Desktop config folders on this Windows machine.

    Covers both install types, because the static %APPDATA%\\Claude path misses
    the Store build:
      - packaged (MSIX / Microsoft Store):
            %LOCALAPPDATA%\\Packages\\Claude_*\\LocalCache\\Roaming\\Claude
      - classic / website installer:
            %APPDATA%\\Claude
    The Store package name carries a publisher hash (e.g. Claude_pzs8sxrjxfjjc)
    that can differ between machines, so we match Claude_* instead of a fixed
    path. Returns only folders that actually exist."""
    dirs: list[Path] = []
    local = os.environ.get("LOCALAPPDATA")
    if local:
        pattern = os.path.join(
            local, "Packages", "Claude_*", "LocalCache", "Roaming", "Claude"
        )
        dirs += [Path(p) for p in glob(pattern)]
    roaming = os.environ.get("APPDATA")
    if roaming:
        dirs.append(Path(roaming) / "Claude")
    return [d for d in dirs if d.is_dir()]


def _windows_config_paths() -> list[Path]:
    """EVERY Claude Desktop config path to write on Windows.

    We don't try to guess which folder the app reads — we write the
    (secret-free) entries to all detected installs (Store + classic), so they
    land wherever Claude actually looks. Falls back to the classic
    %APPDATA%\\Claude on a fresh machine so the installer can still create it."""
    dirs = _windows_claude_dirs()
    if dirs:
        return [d / CLAUDE_CONFIG_NAME for d in dirs]
    base = Path(os.environ.get("APPDATA", Path.home()))
    return [base / "Claude" / CLAUDE_CONFIG_NAME]


def config_path() -> Path:
    """Primary Claude desktop config path for this OS (for display/breadcrumb)."""
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "Claude" / CLAUDE_CONFIG_NAME
    if sys.platform.startswith("win"):
        return _windows_config_paths()[0]
    return home / ".config" / "Claude" / CLAUDE_CONFIG_NAME


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
    where git operations fail). Returns dest/serve.py.

    The update is a clean swap: the fresh copy is staged next to the app
    (`app.new`), the existing .venv (already provisioned deps) is carried
    over, and only then the old app is replaced. Files deleted upstream do
    not survive, and a failure mid-copy leaves the old app untouched."""
    if src.resolve() == dest.resolve():
        return dest / "serve.py"          # already canonical — re-run in place
    dest.parent.mkdir(parents=True, exist_ok=True)
    staging = dest.parent / (dest.name + ".new")
    if staging.exists():
        shutil.rmtree(staging)            # leftover from an interrupted run
    staging.mkdir()
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".venv", ".git")
    for item in RUNTIME_ITEMS:
        s = src / item
        if not s.exists():
            continue
        d = staging / item
        if s.is_dir():
            shutil.copytree(s, d, ignore=ignore)
        else:
            shutil.copy2(s, d)
    # the staged copy is complete — carry the provisioned venv over, then swap
    old_venv = dest / ".venv"
    if old_venv.is_dir():
        shutil.move(str(old_venv), str(staging / ".venv"))
    if dest.exists():
        shutil.rmtree(dest)
    os.replace(staging, dest)
    return dest / "serve.py"


def write_breadcrumb(config_paths: list[Path], entries: dict, serve_path: Path,
                     source: Path) -> Path:
    """Write a visible, secret-free record of the install so it can be verified
    without reading the client's protected config dir (Cowork blocks that).
    Records EVERY config file written (Windows may have several Claude
    installs). Lands at ~/.marketplace-mcp/last_install.json."""
    APP_HOME.mkdir(parents=True, exist_ok=True)
    crumb = APP_HOME / "last_install.json"
    crumb.write_text(json.dumps({
        "installed_at": datetime.now().isoformat(timespec="seconds"),
        "servers": sorted(entries.keys()),
        "serve_py": str(serve_path),
        "installed_from": str(source),
        "client_config": str(config_paths[0]),
        "client_configs": [str(p) for p in config_paths],
        "note": "Verify after restart via MCP tools (wb_check_auth), not by reading the config.",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return crumb


def merge_into_config(cfg_path: Path, cfg_key: str, entries: dict) -> None:
    """Merge the secret-free server entries into one client config file,
    backing up any existing config first. Creates parent dirs as needed.
    The write is atomic (tmp file + os.replace), so a crash mid-write can
    never leave a half-written config behind."""
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    config: dict = {}
    if cfg_path.exists():
        backup = cfg_path.with_suffix(f".json.bak-{datetime.now():%Y%m%d-%H%M%S}")
        shutil.copy2(cfg_path, backup)
        print(f"Backed up existing config → {backup.name}")
        try:
            config = json.loads(cfg_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            n = 1
            while (corrupt := cfg_path.with_name(f"{cfg_path.name}.corrupt-{n}")).exists():
                n += 1
            shutil.copy2(cfg_path, corrupt)
            print(f"\n{'!' * 60}\n"
                  f"⚠️  WARNING: {cfg_path} was NOT valid JSON (corrupt config).\n"
                  f"   The broken file is preserved next to it as: {corrupt.name}\n"
                  f"   A fresh config is being written; review the corrupt copy\n"
                  f"   if you had custom entries there.\n"
                  f"{'!' * 60}\n")
            config = {}
    if not isinstance(config, dict):
        print(f"⚠️  {cfg_path} top level is not a JSON object — replacing it "
              "(old file backed up above).")
        config = {}
    if cfg_key in config and not isinstance(config[cfg_key], dict):
        print(f"⚠️  '{cfg_key}' in {cfg_path.name} is not an object — replacing it "
              "(old file backed up above).")
        config[cfg_key] = {}
    config.setdefault(cfg_key, {})
    config[cfg_key].update(entries)
    tmp = cfg_path.with_name(cfg_path.name + ".tmp")
    tmp.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, cfg_path)


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
    if client in ("claude-code", "codex"):
        # The cabinet store (~/.marketplace-mcp/cabinets.json) is shared by all
        # clients — keys passed as flags must be saved here too, not dropped.
        save_cabinet(args.cabinet, args.wb_token, args.ozon_client_id,
                     args.ozon_api_key, args.ozon_perf_client_id,
                     args.ozon_perf_client_secret)
        saved = [s for s, v in (
            ("WB", args.wb_token),
            ("Ozon", args.ozon_client_id and args.ozon_api_key),
            ("Ozon-Perf", args.ozon_perf_client_id and args.ozon_perf_client_secret),
        ) if v]
        if saved:
            print(f"✅ Cabinet '{args.cabinet}' saved for: {', '.join(saved)} "
                  "(→ ~/.marketplace-mcp/cabinets.json)")
        print(claude_code_commands() if client == "claude-code" else codex_commands())
        return

    entries = build_entries()
    if args.print_only:
        print(json.dumps({"mcpServers": entries}, ensure_ascii=False, indent=2))
        print(f"\n⚠️  Note: this JSON points serve.py at the CURRENT folder "
              f"({HERE}) — if the folder moves or unmounts, the servers break.\n"
              f"   For a stable install run install.py WITHOUT --print: the app "
              f"is copied to {APP_DIR} and the config points there.",
              file=sys.stderr)
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

    # 1b) multi-shop: offer to add more cabinets in one go (interactive only —
    #     skipped when stdin is piped / non-interactive, e.g. CI).
    if sys.stdin and sys.stdin.isatty():
        n = 2
        while _ask("\nAdd another shop? (y/N): ", "").lower() in ("y", "yes", "д", "да"):
            cab = _ask("  Shop (cabinet) name: ", "") or f"shop{n}"
            w2 = _ask("  Wildberries API token (Enter to skip): ", "")
            o2 = _ask("  Ozon Client-Id (Enter to skip): ", "")
            k2 = _ask("  Ozon Api-Key (Enter to skip): ", "")
            save_cabinet(cab, w2, o2, k2, "", "")
            print(f"  ✅ Cabinet '{cab}' saved.")
            n += 1

    # 2) write the (secret-free) server entries to the target client config(s)
    if client == "opencode":
        targets = [opencode_config_path()]; cfg_key = "mcp"; entries = build_opencode_entries()
    elif args.config:
        targets = [Path(args.config)]; cfg_key = "mcpServers"
    elif sys.platform.startswith("win"):
        # Windows: write to EVERY detected Claude install (Store + classic), so
        # the entries land wherever the app actually reads — no guessing.
        targets = _windows_config_paths(); cfg_key = "mcpServers"
    else:  # claude-desktop on macOS / Linux
        targets = [config_path()]; cfg_key = "mcpServers"
    for cfg_path in targets:
        merge_into_config(cfg_path, cfg_key, entries)

    print(f"\n✅ Config ({client}: servers 'wildberries', 'ozon', 'ozon-perf', no secrets):")
    for cfg_path in targets:
        print(f"   • {cfg_path}")
    crumb = write_breadcrumb(targets, entries, SERVE, HERE)
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
