"""Smaller hardening: bounded error `details`, path-param URL-encoding."""
from __future__ import annotations

import asyncio

import httpx

from core.client import MarketplaceClient, ServiceConfig
from core.registry import EndpointSpec


def _route(monkeypatch, handler):
    transport = httpx.MockTransport(handler)
    real_init = httpx.AsyncClient.__init__

    def patched_init(self, *args, **kwargs):
        kwargs["transport"] = transport
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)


def _config():
    return ServiceConfig(
        name="ozon", scheme="https", fields=["client_id", "api_key"],
        env_map={"client_id": "OZON_CLIENT_ID", "api_key": "OZON_API_KEY"},
        build_headers=lambda c: {}, allowed_host_suffixes=[".ozon.ru"])


def test_error_details_are_size_capped(monkeypatch):
    """A huge HTML error page must not be dumped verbatim into the envelope
    (it would flood the agent's context)."""
    huge = "<html>" + "x" * 50_000 + "</html>"

    def handler(request):
        return httpx.Response(500, text=huge, headers={"Content-Type": "text/html"})

    _route(monkeypatch, handler)
    monkeypatch.setenv("OZON_CLIENT_ID", "1")
    monkeypatch.setenv("OZON_API_KEY", "k")
    client = MarketplaceClient(_config())
    r = asyncio.run(client.request("GET", "api-seller.ozon.ru", "/x"))
    assert r["ok"] is False
    assert isinstance(r["details"], str)
    assert len(r["details"]) < 5_000, "details must be capped"


def test_render_path_encodes_special_chars():
    """A path parameter containing '/' or '?' must be percent-encoded so it can't
    redirect the request to a different path/host."""
    spec = EndpointSpec(operation_id="op", method="GET", host="h",
                        path="/v1/item/{id}/info")
    rendered = spec.render_path({"id": "../../evil?x=1"})
    assert "/v1/item/" in rendered
    assert "evil" in rendered
    assert "../" not in rendered  # traversal segment must be encoded away
    assert "?" not in rendered
