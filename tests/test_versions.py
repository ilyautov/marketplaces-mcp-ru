"""One version everywhere: pyproject.toml is the source of truth.

A release ships four version-bearing files (pyproject, server.json with its
package entries, the .mcpb manifest). A mismatch means the registry advertises
an image tag that was never built, or a bundle claiming the wrong version.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _pyproject_version() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    return re.search(r'^version\s*=\s*"([^"]+)"', text, re.M).group(1)


def test_server_json_matches_pyproject():
    v = _pyproject_version()
    sj = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    assert sj["version"] == v
    for pkg in sj["packages"]:
        if pkg["registryType"] == "pypi":
            assert pkg["version"] == v
        elif pkg["registryType"] == "oci":
            assert pkg["identifier"].endswith(f":{v}"), pkg["identifier"]
            assert pkg["identifier"].startswith("ghcr.io/ilyautov/marketplaces-mcp-ru:")
        else:
            raise AssertionError(f"unexpected registryType {pkg['registryType']}")


def test_mcpb_manifest_matches_pyproject():
    v = _pyproject_version()
    manifest = json.loads((ROOT / "mcpb" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["version"] == v


def test_dockerfile_label_matches_server_name():
    sj = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert f'io.modelcontextprotocol.server.name="{sj["name"]}"' in dockerfile


def test_server_json_fits_registry_limits():
    """The MCP Registry rejects server.json with description > 100 chars (422 on
    publish — this bit 0.5.0). Keep title and description within the limit so a
    tag never ships a package the registry will refuse."""
    sj = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    assert len(sj["description"]) <= 100, len(sj["description"])
    assert len(sj["title"]) <= 100, len(sj["title"])
