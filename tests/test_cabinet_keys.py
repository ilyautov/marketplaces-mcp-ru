"""Terminal-free cabinet & key lifecycle (#7): consent gate, auto-naming, upsert.

Tests the plain core functions (the MCP tools are thin wrappers over them).
Async helpers are driven with asyncio.run(), matching the project's test style.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.credentials import CredentialStore  # noqa: E402
from core.tools import _consent_block, _dig, _store_key_core, fetch_shop_name  # noqa: E402


# --- fakes ----------------------------------------------------------------
class FakeSpec:
    def __init__(self, method="GET"):
        self.method = method


class FakeCatalog:
    def __init__(self, spec):
        self._spec = spec

    def get(self, op_id):
        return self._spec


class FakeClient:
    """Minimal client: carries a config and returns a canned call_spec result."""
    def __init__(self, config, result=None, raises=False):
        self.config = config
        self._result = result
        self._raises = raises
        self.last_creds = None

    async def call_spec(self, spec, *, json_body=None, creds_override=None):
        self.last_creds = creds_override
        if self._raises:
            raise RuntimeError("boom")
        return self._result


def make_config(tmp_path, *, name="wb", fields=("token",), whoami=None):
    store = CredentialStore(path=tmp_path / "cabinets.json")
    return SimpleNamespace(name=name, fields=list(fields), store=store, whoami=whoami)


# --- consent gate ---------------------------------------------------------
def test_consent_block_requires_flag():
    block = _consent_block("wb", consent=False)
    assert block and block["error"] == "consent_required"
    assert block["safe_alternative"] == "installer"
    assert _consent_block("wb", consent=True) is None


# --- dotted dig -----------------------------------------------------------
def test_dig_nested_and_missing():
    assert _dig({"result": {"name": "Shop"}}, "result.name") == "Shop"
    assert _dig({"result": {}}, "result.name") is None
    assert _dig("notadict", "a.b") is None


# --- fetch_shop_name ------------------------------------------------------
def test_fetch_shop_name_reads_candidate_field(tmp_path):
    cfg = make_config(tmp_path, whoami=("wb_get_api_seller_info", ["name", "tradeMark"]))
    client = FakeClient(cfg, result={"ok": True, "data": {"tradeMark": "МойБренд"}})
    name = asyncio.run(fetch_shop_name(FakeCatalog(FakeSpec()), client, {"token": "T"}))
    assert name == "МойБренд"
    assert client.last_creds == {"token": "T"}  # used override, not the store


def test_fetch_shop_name_none_on_failure_or_no_whoami(tmp_path):
    cfg = make_config(tmp_path, whoami=("op", ["name"]))
    bad = FakeClient(cfg, result={"ok": False, "error": "auth"})
    assert asyncio.run(fetch_shop_name(FakeCatalog(FakeSpec()), bad, {"token": "T"})) is None
    boom = FakeClient(cfg, raises=True)
    assert asyncio.run(fetch_shop_name(FakeCatalog(FakeSpec()), boom, {"token": "T"})) is None
    cfg2 = make_config(tmp_path, whoami=None)
    assert asyncio.run(fetch_shop_name(FakeCatalog(FakeSpec()), FakeClient(cfg2), {"token": "T"})) is None


# --- _store_key_core ------------------------------------------------------
def _run_store(**kw):
    return asyncio.run(_store_key_core(**kw))


def test_store_key_core_blocks_without_consent(tmp_path):
    cfg = make_config(tmp_path)
    res = _run_store(config=cfg, catalog=None, client=FakeClient(cfg),
                     credentials={"token": "T"}, cabinet="", consent=False)
    assert res["error"] == "consent_required"
    assert cfg.store.list_cabinets("wb")["cabinets"] == []  # nothing written


def test_store_key_core_missing_field(tmp_path):
    cfg = make_config(tmp_path, fields=("client_id", "api_key"), name="ozon")
    res = _run_store(config=cfg, catalog=None, client=FakeClient(cfg),
                     credentials={"client_id": "1"}, cabinet="", consent=True)
    assert res["error"] == "invalid_params" and "api_key" in res["message"]


def test_store_key_core_auto_names_from_shop(tmp_path):
    cfg = make_config(tmp_path, whoami=("op", ["name"]))
    client = FakeClient(cfg, result={"ok": True, "data": {"name": "Магазин Иванова"}})
    res = _run_store(config=cfg, catalog=FakeCatalog(FakeSpec()), client=client,
                     credentials={"token": "T"}, cabinet="", consent=True)
    assert res["ok"] and res["cabinet"] == "Магазин Иванова"
    assert res["validated"] is True
    assert "Магазин Иванова" in cfg.store.list_cabinets("wb")["cabinets"]


def test_store_key_core_falls_back_and_still_saves(tmp_path):
    cfg = make_config(tmp_path, whoami=("op", ["name"]))
    client = FakeClient(cfg, result={"ok": False})  # shop name unavailable
    res = _run_store(config=cfg, catalog=FakeCatalog(FakeSpec()), client=client,
                     credentials={"token": "T"}, cabinet="", consent=True)
    assert res["ok"] and res["cabinet"] == "main"  # fallback name
    assert res["validated"] is False
    assert "main" in cfg.store.list_cabinets("wb")["cabinets"]


def test_store_key_core_explicit_name_wins(tmp_path):
    cfg = make_config(tmp_path, whoami=("op", ["name"]))
    client = FakeClient(cfg, result={"ok": True, "data": {"name": "FromAPI"}})
    res = _run_store(config=cfg, catalog=FakeCatalog(FakeSpec()), client=client,
                     credentials={"token": "T"}, cabinet="мой основной", consent=True)
    assert res["cabinet"] == "мой основной"  # explicit beats API name


# --- the set_key tool is actually registered on the servers ---------------
def test_set_key_tool_registered():
    import wb_mcp.server as wb
    import ozon_mcp.server as oz
    wb_tools = {t.name for t in asyncio.run(wb.mcp.list_tools())}
    oz_tools = {t.name for t in asyncio.run(oz.mcp.list_tools())}
    assert "wb_set_key" in wb_tools
    assert "ozon_set_key" in oz_tools
