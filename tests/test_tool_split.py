"""Исполнители разделены по классу доступа, и это надо удержать.

Один инструмент, умевший и читать, и писать, и удалять, был помечен
разрушительным целиком: подтверждение спрашивалось даже на чтении остатков.
Правила каталога коннекторов Claude такой инструмент вдобавок отклоняют первым
же пунктом. Здесь закреплено и разделение, и аннотации, по которым клиент
решает, спрашивать ли подтверждение.
"""
from __future__ import annotations

import asyncio
import json

from mcp.server.fastmcp import FastMCP

from core.client import MarketplaceClient, ServiceConfig
from core.registry import Catalog, EndpointSpec
from core.tools import register_generic_tools

SPECS = [
    EndpointSpec(operation_id="r", method="GET", host="api-seller.ozon.ru",
                 path="/v1/read", safety="read"),
    EndpointSpec(operation_id="w", method="POST", host="api-seller.ozon.ru",
                 path="/v1/write", safety="write"),
    EndpointSpec(operation_id="d", method="DELETE", host="api-seller.ozon.ru",
                 path="/v1/del", safety="destructive"),
    # Каталог ошибся и пометил удаление чтением: пол по глаголу обязан
    # удержать его подальше от read-only инструмента.
    EndpointSpec(operation_id="lying_delete", method="DELETE",
                 host="api-seller.ozon.ru", path="/v1/oops", safety="read"),
]


def _server():
    cfg = ServiceConfig(
        name="ozon", scheme="https", fields=["client_id", "api_key"],
        env_map={"client_id": "OZON_CLIENT_ID", "api_key": "OZON_API_KEY"},
        build_headers=lambda c: {}, allowed_host_suffixes=[".ozon.ru"])
    mcp = FastMCP("test")
    register_generic_tools(mcp, svc="ozon", client=MarketplaceClient(cfg),
                           catalog=Catalog(SPECS, default_host="api-seller.ozon.ru"))
    return mcp


def _call(mcp, name, args):
    return json.loads(asyncio.run(mcp.call_tool(name, args))[0][0].text)


def _tools(mcp):
    return {t.name: t for t in asyncio.run(mcp.list_tools())}


def test_six_executors_registered():
    names = set(_tools(_server()))
    assert {"ozon_call_method", "ozon_write_method", "ozon_delete_method",
            "ozon_get_raw", "ozon_write_raw", "ozon_delete_raw"} <= names
    # Прежний catch-all не должен вернуться: каталог коннекторов его отклоняет.
    assert "ozon_call_raw" not in names


def test_read_tools_are_annotated_read_only():
    t = _tools(_server())
    for name in ("ozon_call_method", "ozon_get_raw", "ozon_fetch_all"):
        assert t[name].annotations.readOnlyHint is True, name
        assert t[name].annotations.title, name


def test_destructive_tools_are_annotated_destructive():
    t = _tools(_server())
    for name in ("ozon_delete_method", "ozon_delete_raw"):
        assert t[name].annotations.readOnlyHint is False, name
        assert t[name].annotations.destructiveHint is True, name


def test_write_tools_are_not_flagged_destructive():
    t = _tools(_server())
    for name in ("ozon_write_method", "ozon_write_raw"):
        assert t[name].annotations.readOnlyHint is False, name
        assert t[name].annotations.destructiveHint is False, name


def test_read_tool_refuses_a_write_and_names_the_right_one():
    out = _call(_server(), "ozon_call_method", {"operation_id": "w"})
    assert out["error_type"] == "safety_gate"
    assert out["details"]["use_tool"] == "ozon_write_method"
    assert out["details"]["http_call_skipped"] is True


def test_read_tool_refuses_a_delete_mislabelled_as_read():
    """Пол по глаголу поднимает такое до записи (не до удаления: см. _VERB_FLOOR,
    DELETE в черновике бывает обычной записью). Главное, что из read-only
    инструмента оно не уедет."""
    out = _call(_server(), "ozon_call_method", {"operation_id": "lying_delete"})
    assert out["error_type"] == "safety_gate"
    assert out["details"]["use_tool"] == "ozon_write_method"
    assert out["details"]["http_call_skipped"] is True


def test_write_tool_refuses_a_destructive_operation():
    out = _call(_server(), "ozon_write_method",
                {"operation_id": "d", "confirm_write": True})
    assert out["details"]["use_tool"] == "ozon_delete_method"


def test_delete_tool_refuses_a_plain_write():
    out = _call(_server(), "ozon_delete_method",
                {"operation_id": "w", "confirm_write": True,
                 "i_understand_this_modifies_data": True})
    assert out["details"]["use_tool"] == "ozon_write_method"


def test_write_tool_still_needs_confirmation():
    out = _call(_server(), "ozon_write_method", {"operation_id": "w"})
    assert out["error_type"] == "safety_gate"
    assert "confirm_write=true" in out["details"]["required"]


def test_delete_tool_needs_both_confirmations():
    out = _call(_server(), "ozon_delete_method", {"operation_id": "d"})
    assert set(out["details"]["required"]) == {
        "confirm_write=true", "i_understand_this_modifies_data=true"}


def test_raw_read_tool_refuses_an_unsafe_verb():
    out = _call(_server(), "ozon_get_raw", {"path": "/v1/x", "method": "DELETE"})
    assert out["details"]["use_tool"] == "ozon_delete_raw"


def test_raw_write_tool_refuses_delete():
    out = _call(_server(), "ozon_write_raw",
                {"method": "DELETE", "path": "/v1/x", "confirm_write": True})
    assert out["details"]["use_tool"] == "ozon_delete_raw"


def test_raw_write_tool_refuses_get():
    out = _call(_server(), "ozon_write_raw",
                {"method": "GET", "path": "/v1/x", "confirm_write": True})
    assert out["details"]["use_tool"] == "ozon_get_raw"
