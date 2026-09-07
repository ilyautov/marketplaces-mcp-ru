#!/usr/bin/env python3
"""Build the Claude Desktop bundle: dist/marketplaces-mcp-ru-v<VERSION>.mcpb

An .mcpb is a zip a non-technical seller installs with one double-click in
Claude Desktop — no terminal, no Gatekeeper prompt. It carries the manifest at
the root and the runtime under server/. Claude Desktop reads user_config from
the manifest, prompts for the API keys, and injects them as environment
variables the servers read via their env fallback.

    python3 scripts/package_mcpb.py           # build the bundle
    python3 scripts/package_mcpb.py --list     # build, then list contents

The bundle runs `serve.py all`, which mounts WB + Ozon + Ozon-Perf onto one
MCP server. serve.py self-bootstraps its dependencies on first launch, so the
bundle stays small (no vendored site-packages).

Run from anywhere; paths resolve relative to the repo root.
"""
from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path

# Reuse the release packer's allowlist/denylist guards so the two artifacts
# can never diverge on what counts as a secret.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from package_release import (  # noqa: E402
    ROOT,
    assert_clean,
    is_excluded,
    read_name,
    read_version,
    zip_mode,
)

MANIFEST_SRC = ROOT / "mcpb" / "manifest.json"

# Runtime that ships inside the bundle under server/. Only what the server
# needs at import/run time — no install scripts, no docs, no tests.
INCLUDE_DIRS = ["core", "wb_mcp", "ozon_mcp", "ozon_perf_mcp", "yandex_mcp", "avito_mcp"]
INCLUDE_FILES = ["serve.py", "LICENSE"]


def collect_runtime() -> list[Path]:
    out: list[Path] = []
    for d in INCLUDE_DIRS:
        base = ROOT / d
        if not base.exists():
            sys.exit(f"missing required dir: {d}")
        for p in sorted(base.rglob("*")):
            if p.is_file() and not is_excluded(p.relative_to(ROOT).as_posix()):
                out.append(p)
    for f in INCLUDE_FILES:
        p = ROOT / f
        if not p.exists():
            sys.exit(f"missing required file: {f}")
        out.append(p)
    return out


def load_manifest(version: str) -> dict:
    if not MANIFEST_SRC.exists():
        sys.exit(f"manifest not found: {MANIFEST_SRC}")
    manifest = json.loads(MANIFEST_SRC.read_text(encoding="utf-8"))
    # pyproject.toml is the single source of truth for the version — keep the
    # manifest in lockstep so a release can never ship a mismatched version.
    if manifest.get("version") != version:
        print(f"  (synced manifest version {manifest.get('version')} → {version})")
        manifest["version"] = version
    return manifest


def build(list_contents: bool) -> Path:
    version = read_version()
    name = read_name()
    manifest = load_manifest(version)
    files = collect_runtime()
    assert_clean(files)

    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    mcpb_path = dist / f"{name}-v{version}.mcpb"
    if mcpb_path.exists():
        mcpb_path.unlink()

    with zipfile.ZipFile(mcpb_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # manifest.json MUST sit at the archive root.
        info = zipfile.ZipInfo("manifest.json")
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = (0o100000 | 0o644) << 16
        zf.writestr(info, json.dumps(manifest, ensure_ascii=False, indent=2))
        # everything else under server/
        for p in files:
            rel = p.relative_to(ROOT).as_posix()
            info = zipfile.ZipInfo.from_file(p, f"server/{rel}")
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o100000 | zip_mode(p)) << 16
            zf.writestr(info, p.read_bytes())

    size_kb = mcpb_path.stat().st_size / 1024
    print(f"\n✅ Built {mcpb_path.relative_to(ROOT)}  "
          f"({len(files) + 1} entries, {size_kb:.0f} KB)")

    if list_contents:
        print("\nBundle contents:")
        with zipfile.ZipFile(mcpb_path) as zf:
            for n in sorted(zf.namelist()):
                print(f"  {n}")
    return mcpb_path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", action="store_true",
                    help="list bundle contents after build")
    args = ap.parse_args()
    build(args.list)


if __name__ == "__main__":
    main()
