#!/usr/bin/env python3
"""Build a clean, versioned release zip for GitHub distribution.

Reads the version from pyproject.toml and produces:

    dist/marketplace-mcp-v<VERSION>.zip

The archive is a self-contained copy of the project that a non-technical
seller can download, unzip and double-click to install — no .git, no venv,
no secrets, no caches.

    python3 scripts/package_release.py            # build the zip
    python3 scripts/package_release.py --list     # build, then list contents

Run from anywhere; paths are resolved relative to the repo root.
"""
from __future__ import annotations

import argparse
import fnmatch
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# What goes IN — explicit allowlist (top-level entries). Distribution is
# allowlist-driven, not denylist-driven: a forgotten secret can only leak if we
# explicitly add it, which we never do. Missing optional entries are skipped.
INCLUDE_DIRS = [
    "core",
    "wb_mcp",
    "ozon_mcp",
    "ozon_perf_mcp",
    "install-skill",   # optional — added by another agent; skipped if absent
]
INCLUDE_FILES = [
    "install.py",
    "install.command",
    "install.bat",
    "install.sh",
    "serve.py",
    "README.md",
    "QUICKSTART.md",
    "HANDOFF.md",
    "LICENSE",
    "pyproject.toml",
]

# What can never go IN — defense-in-depth denylist applied per file even inside
# an included dir. Anything matching is dropped and reported.
EXCLUDE_PATTERNS = [
    "*/.git", "*/.git/*", ".git/*",
    "*/.venv", "*/.venv/*", ".venv/*",
    "*/__pycache__/*", "__pycache__/*", "*.pyc", "*.pyo",
    "*/.pytest_cache/*", ".pytest_cache/*",
    "*/dist/*", "dist/*",
    "*.egg-info", "*/*.egg-info/*",
    "build/*", "*/build/*",
    "*.env", ".env", "*/.env", "*.env.*",
    "cabinets.json", "*/cabinets.json",
    ".marketplace-mcp/*", "*/.marketplace-mcp/*",
    "*.key", "*.pem", "*.secret", "*credentials.json",
    ".DS_Store", "*/.DS_Store",
]


def read_version() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
    if not m:
        sys.exit("Could not find version in pyproject.toml")
    return m.group(1)


def is_excluded(rel: str) -> bool:
    posix = Path(rel).as_posix()
    for pat in EXCLUDE_PATTERNS:
        if fnmatch.fnmatch(posix, pat) or fnmatch.fnmatch("/" + posix, "*/" + pat):
            return True
    # also catch any path segment that is a denied dir name
    parts = set(Path(posix).parts)
    if parts & {".git", ".venv", "__pycache__", ".pytest_cache", "dist",
                "build", ".marketplace-mcp"}:
        return True
    return False


def collect() -> list[Path]:
    """Gather files to archive from the allowlist, applying the denylist."""
    out: list[Path] = []
    skipped: list[str] = []

    for d in INCLUDE_DIRS:
        base = ROOT / d
        if not base.exists():
            continue
        for p in sorted(base.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(ROOT).as_posix()
            if is_excluded(rel):
                skipped.append(rel)
                continue
            out.append(p)

    for f in INCLUDE_FILES:
        p = ROOT / f
        if not p.exists():
            continue
        rel = p.relative_to(ROOT).as_posix()
        if is_excluded(rel):
            skipped.append(rel)
            continue
        out.append(p)

    if skipped:
        print(f"  (denylist dropped {len(skipped)} path(s), e.g. {skipped[:3]})")
    return out


SECRET_BASENAMES = {"cabinets.json", ".env"}


def assert_clean(files: list[Path]) -> None:
    """Hard guard: refuse to build if anything secret slipped through."""
    bad = []
    for p in files:
        name = p.name
        rel = p.relative_to(ROOT).as_posix()
        if name in SECRET_BASENAMES or name.endswith(".env") or rel.endswith(".pyc"):
            bad.append(rel)
        if any(seg in {".git", ".venv", "__pycache__"} for seg in p.parts):
            bad.append(rel)
    if bad:
        sys.exit(f"REFUSING TO BUILD — secret/junk in file set: {sorted(set(bad))}")


def build(list_contents: bool) -> Path:
    version = read_version()
    files = collect()
    assert_clean(files)

    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    zip_path = dist / f"marketplace-mcp-v{version}.zip"
    if zip_path.exists():
        zip_path.unlink()

    prefix = f"marketplace-mcp-v{version}"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in files:
            rel = p.relative_to(ROOT).as_posix()
            zf.write(p, f"{prefix}/{rel}")

    size_kb = zip_path.stat().st_size / 1024
    print(f"\n✅ Built {zip_path.relative_to(ROOT)}  ({len(files)} files, {size_kb:.0f} KB)")

    if list_contents:
        print("\nArchive contents:")
        with zipfile.ZipFile(zip_path) as zf:
            for n in sorted(zf.namelist()):
                print(f"  {n}")
    return zip_path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", action="store_true", help="list archive contents after build")
    args = ap.parse_args()
    build(args.list)


if __name__ == "__main__":
    main()
