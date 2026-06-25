#!/usr/bin/env python3
"""Windows / Cowork install diagnostic — finds WHERE the config write lands and
whether it matches WHERE Claude Desktop actually reads.

Run it the SAME way you run install.py:
  - inside Cowork (so it sees the same filesystem view install.py sees)
  - AND once from a normal Windows terminal (host view), to compare.

It changes nothing except a tiny probe file it writes then deletes.
"""
from __future__ import annotations

import json
import os
import sys
from glob import glob
from pathlib import Path

CFG = "claude_desktop_config.json"


def line(s: str = "") -> None:
    print(s, flush=True)


def describe(p: Path, label: str) -> None:
    """Report a candidate config dir: existence, the config file, writability."""
    line(f"[{label}] {p}")
    line(f"    dir exists:  {p.is_dir()}")
    cfg = p / CFG
    line(f"    config file: {cfg}  exists={cfg.is_file()}")
    if cfg.is_file():
        try:
            data = json.loads(cfg.read_text(encoding="utf-8"))
            servers = list((data.get("mcpServers") or {}).keys())
            line(f"    mcpServers:  {servers or '(none)'}")
        except Exception as e:  # noqa: BLE001 - diagnostic, surface anything
            line(f"    mcpServers:  <unreadable JSON: {e}>")
    # writability probe — the decisive test for sandbox isolation
    probe = p / ".mcp_write_probe"
    try:
        p.mkdir(parents=True, exist_ok=True)
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        line("    writable:    YES (we can write here)")
    except Exception as e:  # noqa: BLE001
        line(f"    writable:    NO  <{type(e).__name__}: {e}>")
    line()


def main() -> None:
    line("=" * 60)
    line("MARKETPLACE-MCP WINDOWS / COWORK DIAGNOSTIC")
    line("=" * 60)
    line(f"platform:        {sys.platform}")
    line(f"python:          {sys.version.split()[0]}")
    line(f"sys.executable:  {sys.executable}")
    line(f"Path.home():     {Path.home()}")
    line(f"cwd:             {Path.cwd()}")
    line()
    line("Environment as THIS process sees it:")
    for k in ("APPDATA", "LOCALAPPDATA", "USERPROFILE", "HOME"):
        line(f"    {k} = {os.environ.get(k, '(unset)')}")
    line()

    line("-" * 60)
    line("CANDIDATE CONFIG LOCATIONS")
    line("-" * 60)

    # classic / website installer
    appdata = os.environ.get("APPDATA")
    if appdata:
        describe(Path(appdata) / "Claude", "classic %APPDATA%\\Claude")

    # Microsoft Store build(s)
    local = os.environ.get("LOCALAPPDATA")
    if local:
        pattern = os.path.join(local, "Packages", "Claude_*",
                               "LocalCache", "Roaming", "Claude")
        matches = glob(pattern)
        if matches:
            for i, m in enumerate(matches):
                describe(Path(m), f"store match #{i}")
        else:
            line(f"[store] no matches for {pattern}")
            line()

    # linux-ish fallback some builds use
    describe(Path.home() / ".config" / "Claude", "~/.config/Claude")

    # what a previous install.py run claimed it did
    line("-" * 60)
    line("LAST INSTALL BREADCRUMB (~/.marketplace-mcp/last_install.json)")
    line("-" * 60)
    crumb = Path.home() / ".marketplace-mcp" / "last_install.json"
    if crumb.is_file():
        try:
            rec = json.loads(crumb.read_text(encoding="utf-8"))
            line(json.dumps(rec, ensure_ascii=False, indent=2))
            target = Path(rec.get("client_config", ""))
            line()
            line(f"    -> that file exists now? {target.is_file()}")
        except Exception as e:  # noqa: BLE001
            line(f"    <unreadable: {e}>")
    else:
        line("    (no breadcrumb yet — install.py has not run here)")
    line()
    line("=" * 60)
    line("WHAT TO COMPARE:")
    line(" 1. Run this INSIDE Cowork and note the APPDATA value + writable flags.")
    line(" 2. Run it again in a NORMAL Windows terminal (host).")
    line(" 3. If the two APPDATA paths differ, or 'writable: NO' inside Cowork,")
    line("    the write is landing in a sandbox Claude Desktop never reads.")
    line(" 4. The dir whose config shows your real servers = what Claude reads.")
    line("=" * 60)


if __name__ == "__main__":
    main()
