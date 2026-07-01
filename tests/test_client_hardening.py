"""Security & reliability hardening for MarketplaceClient — all offline.

Covers regressions found in review:
  - host allowlist stops credential exfiltration via call_raw host override;
  - path must start with '/' (blocks host smuggling via path);
  - the OAuth token cache is keyed per-credentials (no cross-cabinet leak);
  - a 401 invalidates the cached bearer;
  - a read-phase timeout does NOT auto-retry a mutating verb (no double write);
  - a malformed Retry-After header never crashes the request.
"""
from __future__ import annotations

import asyncio

import httpx
import pytest

from core.client import MarketplaceClient, ServiceConfig, _parse_retry_after


def _static_config(**over) -> ServiceConfig:
    cfg = dict(
        name="ozon",
        scheme="https",
        fields=["client_id", "api_key"],
        env_map={"client_id": "OZON_CLIENT_ID", "api_key": "OZON_API_KEY"},
        build_headers=lambda creds: {"Client-Id": creds.get("client_id", ""),
                                     "Api-Key": creds.get("api_key", "")},
        allowed_host_suffixes=[".ozon.ru"],
    )
    cfg.update(over)
    return ServiceConfig(**cfg)


def _oauth_config(**over) -> ServiceConfig:
    cfg = dict(
        name="ozon_perf",
        scheme="https",
        fields=["client_id", "client_secret"],
        env_map={"client_id": "OZON_PERF_CLIENT_ID",
                 "client_secret": "OZON_PERF_CLIENT_SECRET"},  # pragma: allowlist secret
        build_headers=lambda creds: {"Content-Type": "application/json"},
        token_url="https://api-performance.ozon.ru/api/client/token",
        allowed_host_suffixes=[".ozon.ru"],
    )
    cfg.update(over)
    return ServiceConfig(**cfg)


def _route(monkeypatch, handler):
    transport = httpx.MockTransport(handler)
    real_init = httpx.AsyncClient.__init__

    def patched_init(self, *args, **kwargs):
        kwargs["transport"] = transport
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)


def _no_sleep(monkeypatch):
    async def instant(_):
        return None
    monkeypatch.setattr("core.client.asyncio.sleep", instant)


# --- host allowlist ---------------------------------------------------------

def test_host_outside_allowlist_is_refused_and_no_request_sent(monkeypatch):
    hits = {"n": 0}

    def handler(request):
        hits["n"] += 1
        return httpx.Response(200, json={"ok": True})

    _route(monkeypatch, handler)
    monkeypatch.setenv("OZON_CLIENT_ID", "100")
    monkeypatch.setenv("OZON_API_KEY", "secret")
    client = MarketplaceClient(_static_config())

    r = asyncio.run(client.request("GET", "evil.example.com", "/steal"))
    assert r["ok"] is False
    assert r["error_type"] in ("forbidden", "invalid_params")
    assert hits["n"] == 0, "no HTTP request may reach a non-allowlisted host"


def test_host_suffix_smuggling_is_refused(monkeypatch):
    """api-seller.ozon.ru.evil.com must NOT pass a '.ozon.ru' suffix check."""
    _route(monkeypatch, lambda req: httpx.Response(200, json={}))
    monkeypatch.setenv("OZON_CLIENT_ID", "100")
    monkeypatch.setenv("OZON_API_KEY", "secret")
    client = MarketplaceClient(_static_config())
    r = asyncio.run(client.request("GET", "api-seller.ozon.ru.evil.com", "/x"))
    assert r["ok"] is False


def test_path_must_start_with_slash(monkeypatch):
    """A path not starting with '/' could smuggle a new host onto the URL."""
    hits = {"n": 0}

    def handler(request):
        hits["n"] += 1
        return httpx.Response(200, json={})

    _route(monkeypatch, handler)
    monkeypatch.setenv("OZON_CLIENT_ID", "100")
    monkeypatch.setenv("OZON_API_KEY", "secret")
    client = MarketplaceClient(_static_config())
    r = asyncio.run(client.request("GET", "api-seller.ozon.ru", ".evil.com/x"))
    assert r["ok"] is False
    assert hits["n"] == 0


def test_allowlisted_host_still_works(monkeypatch):
    _route(monkeypatch, lambda req: httpx.Response(200, json={"data": 1}))
    monkeypatch.setenv("OZON_CLIENT_ID", "100")
    monkeypatch.setenv("OZON_API_KEY", "secret")
    client = MarketplaceClient(_static_config())
    r = asyncio.run(client.request("GET", "api-seller.ozon.ru", "/v1/x"))
    assert r["ok"] is True


# --- token cache keyed per credentials --------------------------------------

class _TokenRec:
    def __init__(self):
        self.token_seq = 0
        self.seen_auth = []

    def handler(self, request):
        if request.url.path == "/api/client/token":
            self.token_seq += 1
            return httpx.Response(200, json={
                "access_token": f"TKN-{self.token_seq}",
                "expires_in": 1800, "token_type": "Bearer"})
        self.seen_auth.append(request.headers.get("Authorization", ""))
        return httpx.Response(200, json={"ok": True})


def test_token_cache_is_keyed_per_credentials(monkeypatch):
    """Switching credentials must fetch a fresh token, not reuse the cached one
    from the previous cabinet."""
    rec = _TokenRec()
    _route(monkeypatch, rec.handler)
    client = MarketplaceClient(_oauth_config())

    creds_a = {"client_id": "A", "client_secret": "sa"}  # pragma: allowlist secret
    creds_b = {"client_id": "B", "client_secret": "sb"}  # pragma: allowlist secret

    async def run():
        await client.request("GET", "api-performance.ozon.ru", "/x",
                             creds_override=creds_a)
        await client.request("GET", "api-performance.ozon.ru", "/x",
                             creds_override=creds_a)  # reuse A's token
        await client.request("GET", "api-performance.ozon.ru", "/x",
                             creds_override=creds_b)  # new token for B

    asyncio.run(run())
    assert rec.token_seq == 2, f"expected 2 token fetches, got {rec.token_seq}"
    assert rec.seen_auth == ["Bearer TKN-1", "Bearer TKN-1", "Bearer TKN-2"]


def test_401_invalidates_cached_token(monkeypatch):
    rec = _TokenRec()
    state = {"first": True}

    def handler(request):
        if request.url.path == "/api/client/token":
            return rec.handler(request)
        rec.seen_auth.append(request.headers.get("Authorization", ""))
        if state["first"]:
            state["first"] = False
            return httpx.Response(401, json={"error": "expired"})
        return httpx.Response(200, json={"ok": True})

    _route(monkeypatch, handler)
    _no_sleep(monkeypatch)
    client = MarketplaceClient(_oauth_config())
    creds = {"client_id": "A", "client_secret": "sa"}  # pragma: allowlist secret

    async def run():
        await client.request("GET", "api-performance.ozon.ru", "/x",
                             creds_override=creds)  # 401 -> drop token
        await client.request("GET", "api-performance.ozon.ru", "/x",
                             creds_override=creds)  # must refetch a token

    asyncio.run(run())
    assert rec.token_seq == 2, "a 401 must invalidate the cached bearer"


# --- retry safety on write verbs --------------------------------------------

def test_read_timeout_does_not_retry_a_write(monkeypatch):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        raise httpx.ReadTimeout("slow", request=request)

    _route(monkeypatch, handler)
    _no_sleep(monkeypatch)
    monkeypatch.setenv("OZON_CLIENT_ID", "100")
    monkeypatch.setenv("OZON_API_KEY", "secret")
    client = MarketplaceClient(_static_config())
    r = asyncio.run(client.request("POST", "api-seller.ozon.ru", "/v1/supply/create"))
    assert r["ok"] is False
    assert calls["n"] == 1, "a POST must not be auto-retried after a read timeout"


def test_read_timeout_does_retry_a_get(monkeypatch):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        raise httpx.ReadTimeout("slow", request=request)

    _route(monkeypatch, handler)
    _no_sleep(monkeypatch)
    monkeypatch.setenv("OZON_CLIENT_ID", "100")
    monkeypatch.setenv("OZON_API_KEY", "secret")
    client = MarketplaceClient(_static_config())
    asyncio.run(client.request("GET", "api-seller.ozon.ru", "/v1/list"))
    assert calls["n"] > 1, "a GET is safe to retry after a read timeout"


def test_connect_error_retries_even_for_write(monkeypatch):
    """A connection-phase failure means the request never reached the server —
    safe to retry any verb."""
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        raise httpx.ConnectError("refused", request=request)

    _route(monkeypatch, handler)
    _no_sleep(monkeypatch)
    monkeypatch.setenv("OZON_CLIENT_ID", "100")
    monkeypatch.setenv("OZON_API_KEY", "secret")
    client = MarketplaceClient(_static_config())
    asyncio.run(client.request("POST", "api-seller.ozon.ru", "/v1/x"))
    assert calls["n"] > 1


# --- malformed Retry-After --------------------------------------------------

def test_malformed_retry_after_does_not_crash():
    assert _parse_retry_after("soon") is None
    assert _parse_retry_after("") is None
    assert _parse_retry_after(None) is None
    assert _parse_retry_after("120") == pytest.approx(120.0)


def test_429_with_garbage_retry_after_falls_back_to_backoff(monkeypatch):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "later"},
                                  json={"error": "slow down"})
        return httpx.Response(200, json={"ok": True})

    _route(monkeypatch, handler)
    _no_sleep(monkeypatch)
    monkeypatch.setenv("OZON_CLIENT_ID", "100")
    monkeypatch.setenv("OZON_API_KEY", "secret")
    client = MarketplaceClient(_static_config())
    r = asyncio.run(client.request("GET", "api-seller.ozon.ru", "/x"))
    assert r["ok"] is True
    assert calls["n"] == 2
