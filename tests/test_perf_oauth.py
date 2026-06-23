"""OAuth2 client_credentials flow for the Ozon Performance server — offline.

No live tokens, no real network: an httpx.MockTransport answers both the token
endpoint and one API call. We assert that:
  - the bearer token is fetched exactly ONCE and reused (cached) for N calls;
  - every API request carries "Authorization: Bearer <token>";
  - the token request body is the documented client_credentials payload;
  - an expired token triggers exactly one refresh.

NOTE: the Ozon Performance token contract is DOCUMENTED but UNVERIFIED live
(no perf creds at build time). These tests pin the contract we coded against;
if the live API differs, update core.client.MarketplaceClient._fetch_token.
"""
from __future__ import annotations

import asyncio
import time

import httpx
import pytest

from core.client import MarketplaceClient, ServiceConfig


TOKEN_URL = "https://api-performance.ozon.ru/api/client/token"
API_HOST = "api-performance.ozon.ru"
API_PATH = "/api/client/campaign"


def _make_config() -> ServiceConfig:
    return ServiceConfig(
        name="ozon_perf",
        scheme="https",
        fields=["client_id", "client_secret"],
        env_map={"client_id": "OZON_PERF_CLIENT_ID",
                 "client_secret": "OZON_PERF_CLIENT_SECRET"},
        build_headers=lambda creds: {"Content-Type": "application/json"},
        token_url=TOKEN_URL,
    )


class _Recorder:
    """Counts token vs API hits and captures the Authorization header sent."""
    def __init__(self, expires_in: int = 1800, access_token: str = "TKN-1"):
        self.token_calls = 0
        self.api_calls = 0
        self.seen_auth: list[str] = []
        self.token_payloads: list[dict] = []
        self.expires_in = expires_in
        self.access_token = access_token

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/client/token":
            self.token_calls += 1
            import json as _json
            self.token_payloads.append(_json.loads(request.content.decode() or "{}"))
            return httpx.Response(200, json={
                "access_token": self.access_token,
                "expires_in": self.expires_in,
                "token_type": "Bearer",
            })
        # API endpoint
        self.api_calls += 1
        self.seen_auth.append(request.headers.get("Authorization", ""))
        return httpx.Response(200, json={"list": [{"id": 1}]})


def _patch_async_client(monkeypatch, recorder: _Recorder):
    """Force every httpx.AsyncClient(...) to route through the MockTransport."""
    transport = httpx.MockTransport(recorder.handler)
    real_init = httpx.AsyncClient.__init__

    def patched_init(self, *args, **kwargs):
        kwargs["transport"] = transport
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)


def _creds(monkeypatch):
    monkeypatch.setenv("OZON_PERF_CLIENT_ID", "cid-123")
    monkeypatch.setenv("OZON_PERF_CLIENT_SECRET", "secret-xyz")


def test_token_fetched_once_and_cached(monkeypatch):
    _creds(monkeypatch)
    rec = _Recorder()
    _patch_async_client(monkeypatch, rec)
    client = MarketplaceClient(_make_config())

    async def run():
        r1 = await client.request("GET", API_HOST, API_PATH)
        r2 = await client.request("GET", API_HOST, API_PATH)
        r3 = await client.request("GET", API_HOST, API_PATH)
        return r1, r2, r3

    r1, r2, r3 = asyncio.run(run())
    # all three API calls succeeded
    for r in (r1, r2, r3):
        assert r["ok"] is True and r["status"] == 200
    # token fetched exactly once, reused for all three API calls
    assert rec.token_calls == 1, f"expected 1 token call, got {rec.token_calls}"
    assert rec.api_calls == 3
    # every API request carried the bearer
    assert rec.seen_auth == ["Bearer TKN-1"] * 3


def test_token_request_payload_is_client_credentials(monkeypatch):
    _creds(monkeypatch)
    rec = _Recorder()
    _patch_async_client(monkeypatch, rec)
    client = MarketplaceClient(_make_config())
    asyncio.run(client.request("GET", API_HOST, API_PATH))
    assert rec.token_payloads[0] == {
        "client_id": "cid-123",
        "client_secret": "secret-xyz",
        "grant_type": "client_credentials",
    }


def test_expired_token_triggers_one_refresh(monkeypatch):
    _creds(monkeypatch)
    # expires_in tiny so the 60s skew makes it already-expired on cache.
    rec = _Recorder(expires_in=1)
    _patch_async_client(monkeypatch, rec)
    client = MarketplaceClient(_make_config())

    async def run():
        await client.request("GET", API_HOST, API_PATH)  # fetch #1
        await client.request("GET", API_HOST, API_PATH)  # expired -> fetch #2
        return None

    asyncio.run(run())
    assert rec.token_calls == 2, f"expected 2 token calls, got {rec.token_calls}"
    assert rec.api_calls == 2


def test_static_service_does_not_call_token_endpoint(monkeypatch):
    """A non-OAuth service (token_url='') must never hit a token endpoint and
    must keep using its static build_headers (regression guard)."""
    rec = _Recorder()
    _patch_async_client(monkeypatch, rec)
    cfg = ServiceConfig(
        name="ozon",
        scheme="https",
        fields=["client_id", "api_key"],
        env_map={"client_id": "OZON_CLIENT_ID", "api_key": "OZON_API_KEY"},
        build_headers=lambda creds: {"Client-Id": creds.get("client_id", ""),
                                     "Api-Key": creds.get("api_key", "")},
    )
    monkeypatch.setenv("OZON_CLIENT_ID", "100")
    monkeypatch.setenv("OZON_API_KEY", "k")
    client = MarketplaceClient(cfg)
    r = asyncio.run(client.request("GET", "api-seller.ozon.ru", "/v1/x"))
    assert r["ok"] is True
    assert rec.token_calls == 0  # no OAuth
    # static service sends no Bearer; it used Client-Id/Api-Key instead
    assert rec.seen_auth == [""]
