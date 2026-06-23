"""Offline verification — no live tokens, no network.

Covers: catalog loading + search, path rendering, safety gating, error
envelope, auto-pagination (offset + last_id), header building, and that both
servers register their full tool set.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from core.client import MarketplaceClient
from core.errors import classify_status, make_error
from core.paginate import fetch_all
from core.registry import Catalog
from core.safety import check_gate, infer_safety

ROOT = Path(__file__).resolve().parent.parent
WB_YAML = ROOT / "wb_mcp" / "endpoints.yaml"
OZON_YAML = ROOT / "ozon_mcp" / "endpoints.yaml"


# ----------------------------- catalog -----------------------------
def test_catalogs_load_and_are_nonempty():
    wb = Catalog.from_yaml(WB_YAML)
    ozon = Catalog.from_yaml(OZON_YAML)
    assert len(wb.all()) >= 25
    assert len(ozon.all()) >= 25
    # every spec has a host (WB is multi-host; none may be blank)
    for c in (wb, ozon):
        for s in c.all():
            assert s.host, f"{s.operation_id} has no host"
            assert s.method in {"GET", "POST", "PUT", "PATCH", "DELETE"}
            assert s.safety in {"read", "write", "destructive"}


def test_search_ru_and_en():
    wb = Catalog.from_yaml(WB_YAML)
    assert any("stocks" in s.operation_id for s in wb.search("остатки"))
    assert any("sales" in s.operation_id for s in wb.search("sales returns"))
    ozon = Catalog.from_yaml(OZON_YAML)
    assert any("price" in s.operation_id for s in ozon.search("цена price"))


def test_path_rendering():
    wb = Catalog.from_yaml(WB_YAML)
    spec = wb.get("wb_content_charcs")
    assert spec.path_params == ["subjectId"]
    assert spec.render_path({"subjectId": 42}).endswith("/42")
    with pytest.raises(KeyError):
        spec.render_path({})


# ----------------------------- safety -----------------------------
def test_safety_gate_levels():
    # read passes
    assert check_gate("read", confirm_write=False,
                      i_understand_this_modifies_data=False) is None
    # write blocked without confirm
    assert check_gate("write", confirm_write=False,
                      i_understand_this_modifies_data=False)["error"] == "safety_gate"
    # write passes with confirm
    assert check_gate("write", confirm_write=True,
                      i_understand_this_modifies_data=False) is None
    # destructive needs both
    assert check_gate("destructive", confirm_write=True,
                      i_understand_this_modifies_data=False)["error"] == "safety_gate"
    assert check_gate("destructive", confirm_write=True,
                      i_understand_this_modifies_data=True) is None


def test_verb_inference():
    assert infer_safety("GET", None) == "read"
    assert infer_safety("DELETE", None) == "destructive"
    assert infer_safety("POST", "read") == "read"  # catalog override wins


# ----------------------------- errors -----------------------------
def test_status_classification():
    assert classify_status(429) == ("rate_limit", True)
    assert classify_status(403) == ("forbidden", False)
    assert classify_status(503) == ("server_error", True)
    env = make_error("auth", "no creds")
    assert env["ok"] is False and env["retryable"] is False


# ----------------------------- credentials / headers -----------------------------
def test_missing_creds_envelope(monkeypatch):
    monkeypatch.delenv("WB_API_TOKEN", raising=False)
    from wb_mcp.server import client as wb_client
    creds, err = wb_client._creds_or_error()
    assert creds is None and err["error"] == "auth"


def test_header_building(monkeypatch):
    monkeypatch.setenv("OZON_CLIENT_ID", "123")
    monkeypatch.setenv("OZON_API_KEY", "secret-key")
    from ozon_mcp.server import OZON_CONFIG
    headers = OZON_CONFIG.build_headers(OZON_CONFIG.load_creds({
        "OZON_CLIENT_ID": "123", "OZON_API_KEY": "secret-key"}))
    assert headers["Client-Id"] == "123"
    assert headers["Api-Key"] == "secret-key"


# ----------------------------- pagination (fake client) -----------------------------
class _FakeClient:
    """Returns canned pages so we exercise the walker without network."""
    def __init__(self, pages):
        self._pages = pages
        self.calls = 0

    async def call_spec(self, spec, path_values=None, query=None, json_body=None):
        page = self._pages[min(self.calls, len(self._pages) - 1)]
        self.calls += 1
        return {"ok": True, "status": 200, "data": page}


def test_fetch_all_offset():
    wb = Catalog.from_yaml(WB_YAML)
    spec = wb.get("wb_prices_list")  # pagination: offset
    pages = [
        {"result": {"items": [1, 2, 3]}},
        {"result": {"items": [4, 5]}},  # short page -> stop
    ]
    fake = _FakeClient(pages)
    out = asyncio.run(fetch_all(fake, spec, items_path="result.items", limit=3))
    assert out["total_fetched"] == 5
    assert out["truncated"] is False


def test_fetch_all_last_id():
    ozon = Catalog.from_yaml(OZON_YAML)
    spec = ozon.get("ozon_product_list")  # pagination: last_id
    pages = [
        {"result": {"items": [{"id": 1}], "last_id": "a"}},
        {"result": {"items": [{"id": 2}], "last_id": "a"}},  # repeated cursor -> stop
    ]
    fake = _FakeClient(pages)
    out = asyncio.run(fetch_all(fake, spec, items_path="result.items", limit=1))
    assert out["total_fetched"] == 2


# ----------------------------- tool registration -----------------------------
def test_servers_register_tools():
    from wb_mcp.server import mcp as wb_mcp
    from ozon_mcp.server import mcp as ozon_mcp
    wb_tools = {t.name for t in asyncio.run(wb_mcp.list_tools())}
    ozon_tools = {t.name for t in asyncio.run(ozon_mcp.list_tools())}
    # 8 generic + typed convenience tools
    for t in ("wb_search_methods", "wb_call_method", "wb_call_raw",
              "wb_fetch_all", "wb_get_sales", "wb_set_price"):
        assert t in wb_tools, f"missing {t}"
    for t in ("ozon_search_methods", "ozon_call_method", "ozon_call_raw",
              "ozon_fetch_all", "ozon_get_products", "ozon_set_price"):
        assert t in ozon_tools, f"missing {t}"
    assert len(wb_tools) >= 13 and len(ozon_tools) >= 13


# ----------------------------- cross-platform install -----------------------------
def test_config_path_per_os(monkeypatch):
    import install
    monkeypatch.setattr(install.sys, "platform", "darwin")
    assert install.config_path().name == "claude_desktop_config.json"
    assert "Application Support" in str(install.config_path())
    monkeypatch.setattr(install.sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", r"C:\Users\u\AppData\Roaming")
    assert "Roaming" in str(install.config_path()).replace("/", "\\") or \
           "Claude" in str(install.config_path())
    monkeypatch.setattr(install.sys, "platform", "linux")
    assert ".config" in str(install.config_path())


def test_serve_venv_python_per_os(monkeypatch):
    import serve
    monkeypatch.setattr(serve.os, "name", "nt")
    assert serve._venv_python().name == "python.exe"
    assert "Scripts" in str(serve._venv_python())
    monkeypatch.setattr(serve.os, "name", "posix")
    assert serve._venv_python().name == "python"
    assert "bin" in str(serve._venv_python())


def test_claude_code_commands():
    import install
    out = install.claude_code_commands("WBTOK", "CID", "AKEY")
    assert "claude mcp add wildberries" in out
    assert "claude mcp add ozon" in out
    assert "WBTOK" in out and "CID" in out and "AKEY" in out
