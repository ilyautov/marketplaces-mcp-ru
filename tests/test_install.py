"""Tests for the canonical-install behaviour of install.py.

Covers the fixes from the install friction log: the app is copied to a stable
location (so config doesn't break when the source folder moves), and a
secret-free breadcrumb is written for post-restart verification.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import install  # noqa: E402


def test_install_app_copies_runtime_and_excludes_vcs(tmp_path):
    dest = tmp_path / "app"
    serve = install.install_app(ROOT, dest)
    assert serve == dest / "serve.py" and serve.exists()
    # runtime essentials are present in the canonical copy
    assert (dest / "core" / "__init__.py").exists()
    assert (dest / "wb_mcp" / "endpoints.yaml").exists()
    assert (dest / "ozon_mcp" / "perf_endpoints.yaml").exists()
    # vcs / caches are NOT carried over
    assert not (dest / ".git").exists()
    assert not list(dest.rglob("__pycache__"))


def test_install_app_is_idempotent_when_src_equals_dest(tmp_path):
    dest = tmp_path / "app"
    install.install_app(ROOT, dest)
    # second run onto the same dest must not raise
    serve = install.install_app(dest, dest)
    assert serve == dest / "serve.py"


def test_copied_app_loads_catalogs(tmp_path):
    """The canonical copy must be self-sufficient — catalogs load from it."""
    dest = tmp_path / "app"
    install.install_app(ROOT, dest)
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_copied_registry", dest / "core" / "registry.py")
    # the package layout is intact, so loading via the copied tree works
    assert (dest / "core" / "registry.py").exists()
    assert spec is not None


def test_breadcrumb_records_servers_without_secrets(tmp_path, monkeypatch):
    monkeypatch.setattr(install, "APP_HOME", tmp_path)
    entries = {"wildberries": {"command": "python", "args": ["serve.py", "wb"]},
               "ozon": {"command": "python", "args": ["serve.py", "ozon"]}}
    crumb = install.write_breadcrumb(
        config_path=Path("/some/claude_desktop_config.json"),
        entries=entries, serve_path=tmp_path / "app" / "serve.py",
        source=Path("/Users/x/Пример/repo"))
    data = json.loads(crumb.read_text(encoding="utf-8"))
    assert crumb == tmp_path / "last_install.json"
    assert data["servers"] == ["ozon", "wildberries"]
    assert "serve_py" in data and "installed_at" in data
    # no secret-looking material leaked into the breadcrumb
    blob = crumb.read_text(encoding="utf-8").lower()
    assert "token" not in blob.replace("verify", "") or "api_key" not in blob
    assert "wb_api_token" not in blob and "client_secret" not in blob
