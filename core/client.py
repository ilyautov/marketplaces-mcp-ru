"""Async HTTP client shared by every marketplace server.

Responsibilities:
- Load credentials from environment variables (never from code/args).
- Build service-specific auth headers.
- Execute a request described by an EndpointSpec (or a raw path).
- Retry on 429 with exponential backoff, honouring Retry-After.
- Return parsed JSON on success, or the canonical error envelope on failure.

Service differences (WB vs Ozon) are isolated in a ServiceConfig object so the
request/backoff/pagination logic is written exactly once.
"""
from __future__ import annotations

import asyncio
import email.utils
import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import httpx

from .credentials import CredentialStore
from .errors import classify_status, error_from_exception, make_error
from .registry import EndpointSpec

DEFAULT_TIMEOUT = 30.0
MAX_RETRIES = 4
BACKOFF_BASE = 1.5  # seconds; * 2**attempt


@dataclass
class ServiceConfig:
    """Per-service wiring. Keeps all WB/Ozon specifics out of the engine.

    Credentials are resolved per service from the cabinet store (active cabinet),
    falling back to environment variables for an env-only install.
    """
    name: str                                   # "wb" | "ozon" | "ozon_perf"
    scheme: str                                 # "https"
    fields: list[str]                           # cabinet field names (e.g. ["client_id","api_key"])
    env_map: dict[str, str]                      # field -> ENV var for fallback
    # headers(creds) -> dict of HTTP headers (auth). For OAuth services (token_url
    # set) this is ignored for auth; the bearer header is injected automatically.
    build_headers: Callable[[dict[str, str]], dict[str, str]]
    store: CredentialStore = field(default_factory=CredentialStore)
    user_agent: str = "marketplace-mcp/0.1 (+https://github.com/)"
    # Host allowlist: a request may only be sent to a host whose name equals or
    # ends with one of these suffixes (e.g. ".ozon.ru", ".wildberries.ru"). This
    # stops a compromised/mis-prompted agent from exfiltrating the cabinet's auth
    # headers to an attacker host via {svc}_call_raw. Empty list = no allowlist
    # (permissive; the real servers always set one).
    allowed_host_suffixes: list[str] = field(default_factory=list)
    # --- OAuth2 client_credentials (optional) -------------------------------
    # When token_url is non-empty the client treats this service as OAuth2
    # client_credentials: it POSTs creds to token_url, caches the access_token,
    # and sends "Authorization: Bearer <token>" on every request. When token_url
    # is "" (WB, Ozon Seller) nothing changes — static build_headers as before.
    token_url: str = ""
    # which cred field feeds the token request's client_id / client_secret.
    oauth_id_field: str = "client_id"
    oauth_secret_field: str = "client_secret"
    # Optional "whoami" lookup for auto-naming a cabinet from the marketplace's
    # own seller-info endpoint: (operation_id, [candidate dotted name fields]).
    # None disables auto-naming for this service.
    whoami: Optional[tuple[str, list[str]]] = None

    @property
    def is_oauth(self) -> bool:
        return bool(self.token_url)

    def resolve_creds(self) -> tuple[dict[str, str], str]:
        return self.store.resolve(self.name, self.fields, self.env_map)

    def missing_creds(self) -> list[str]:
        return self.store.missing(self.name, self.fields, self.env_map)

    def host_allowed(self, host: str) -> bool:
        """True if `host` is inside the service allowlist (or no allowlist set).

        Suffix match is anchored on a dot boundary so `api-seller.ozon.ru.evil.com`
        does NOT match `.ozon.ru`.
        """
        if not self.allowed_host_suffixes:
            return True
        h = host.strip().lower()
        for pre in ("https://", "http://"):
            if h.startswith(pre):
                h = h[len(pre):]
        h = h.strip("/").split("/")[0].split(":")[0]
        for suf in self.allowed_host_suffixes:
            bare = suf.lstrip(".")
            if h == bare or h.endswith("." + bare):
                return True
        return False


def _parse_retry_after(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    try:
        return float(value)  # delta-seconds
    except ValueError:
        pass
    # HTTP-date form. parsedate_to_datetime raises (not returns None) on garbage
    # in Python >= 3.10, so guard it — a bad header must never crash the request.
    try:
        dt = email.utils.parsedate_to_datetime(value)
    except (ValueError, TypeError):
        return None
    if dt is None:
        return None
    return max(0.0, dt.timestamp() - time.time())


# Refresh a cached bearer this many seconds BEFORE it actually expires, so an
# in-flight request never races the expiry boundary.
TOKEN_EXPIRY_SKEW = 60.0


class MarketplaceClient:
    def __init__(self, config: ServiceConfig):
        self.config = config
        # OAuth token cache (only used when config.token_url is set). Keyed per
        # credential set so switching cabinets never reuses another cabinet's
        # bearer: {creds_key: (token, monotonic_expiry)}.
        self._tokens: dict[str, tuple[str, float]] = {}
        self._token_lock = asyncio.Lock()

    @staticmethod
    def _creds_key(config: ServiceConfig, creds: dict[str, str]) -> str:
        raw = json.dumps({f: creds.get(f, "") for f in config.fields},
                         sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    # --- credential handling -------------------------------------------------
    def _creds_or_error(self) -> tuple[Optional[dict[str, str]], Optional[dict]]:
        creds, _source = self.config.resolve_creds()
        missing = [f for f in self.config.fields if not creds.get(f)]
        if missing:
            return None, make_error(
                "auth",
                f"Missing credentials for fields: {', '.join(missing)}. "
                f"Add a cabinet with {self.config.name}_add_cabinet, run install.py, "
                "or set the matching environment variables.",
                retryable=False,
            )
        return creds, None

    # --- OAuth2 client_credentials ------------------------------------------
    # NOTE: the Ozon Performance token contract below is DOCUMENTED but NOT yet
    # verified against the live API (no perf credentials available at build time).
    # Documented contract:
    #   POST {token_url}  JSON {client_id, client_secret, grant_type:
    #   "client_credentials"}  ->  200 {"access_token","expires_in",
    #   "token_type":"Bearer"}.
    # If the live API differs (field names, form-encoding instead of JSON, a
    # different token_type, etc.) adjust _fetch_token below — this is the single
    # place that has to change.
    async def _ensure_token(self, creds: dict[str, str]) -> tuple[Optional[str], Optional[dict]]:
        """Return (bearer_token, None) or (None, error_envelope).

        Uses a cached token while valid; refreshes (with a 60s skew) on expiry.
        Concurrency-safe: a lock prevents a token stampede across parallel calls.
        """
        key = self._creds_key(self.config, creds)
        now = time.monotonic()
        cached = self._tokens.get(key)
        if cached and now < cached[1]:
            return cached[0], None
        async with self._token_lock:
            # Re-check inside the lock: another coroutine may have refreshed.
            cached = self._tokens.get(key)
            now = time.monotonic()
            if cached and now < cached[1]:
                return cached[0], None
            return await self._fetch_token(creds, key)

    async def _fetch_token(self, creds: dict[str, str],
                           key: str) -> tuple[Optional[str], Optional[dict]]:
        cfg = self.config
        payload = {
            "client_id": creds.get(cfg.oauth_id_field, ""),
            "client_secret": creds.get(cfg.oauth_secret_field, ""),
            "grant_type": "client_credentials",
        }
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                resp = await client.post(
                    cfg.token_url,
                    json=payload,
                    headers={"User-Agent": cfg.user_agent,
                             "Content-Type": "application/json",
                             "Accept": "application/json"},
                )
        except Exception as exc:  # noqa: BLE001
            return None, error_from_exception(
                exc, operation_id="oauth_token", endpoint=cfg.token_url)

        if not resp.is_success:
            etype, retryable = classify_status(resp.status_code)
            return None, make_error(
                etype,
                f"{cfg.name.upper()} token endpoint returned {resp.status_code}: "
                f"{_short_body(resp)}",
                code=resp.status_code,
                operation_id="oauth_token",
                endpoint=cfg.token_url,
                retryable=retryable,
            )
        body = _parse_body(resp)
        if not isinstance(body, dict) or not body.get("access_token"):
            # ASSUMPTION: token lives under "access_token". Unverified live.
            return None, make_error(
                "auth",
                f"{cfg.name.upper()} token response had no access_token: "
                f"{str(body)[:200]}",
                operation_id="oauth_token",
                endpoint=cfg.token_url,
                retryable=False,
            )
        token = body["access_token"]
        # expires_in is seconds; default to 1800 (documented) if absent. Cache
        # with a safety skew so we refresh slightly early.
        try:
            ttl = float(body.get("expires_in", 1800))
        except (TypeError, ValueError):
            ttl = 1800.0
        self._tokens[key] = (token, time.monotonic() + max(0.0, ttl - TOKEN_EXPIRY_SKEW))
        return token, None

    def _invalidate_token(self, creds: dict[str, str]) -> None:
        self._tokens.pop(self._creds_key(self.config, creds), None)

    def _url(self, host: str, path: str) -> str:
        h = host.strip()
        for pre in ("https://", "http://"):
            if h.startswith(pre):
                h = h[len(pre):]
        h = h.strip("/")
        return f"{self.config.scheme}://{h}{path}"

    # --- core request --------------------------------------------------------
    async def request(
        self,
        method: str,
        host: str,
        path: str,
        *,
        query: Optional[dict[str, Any]] = None,
        json_body: Optional[Any] = None,
        operation_id: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
        creds_override: Optional[dict[str, str]] = None,
    ) -> dict:
        """Execute one HTTP request with 429 backoff. Returns a dict:
        success -> {"ok": True, "status": int, "data": <parsed json|text>}
        failure -> canonical error envelope (ok=False).

        creds_override lets a caller authenticate with an explicit credential set
        (e.g. validating a not-yet-stored key) instead of the active cabinet.
        """
        if not isinstance(path, str) or not path.startswith("/"):
            return make_error(
                "invalid_params",
                f"path must be a string beginning with '/', got {path!r}. "
                "A path that does not start with '/' can smuggle a different host "
                "onto the URL — refused before sending.",
                operation_id=operation_id, endpoint=path, retryable=False,
            )
        if not self.config.host_allowed(host):
            return make_error(
                "forbidden",
                f"Host {host!r} is not in the {self.config.name} allowlist "
                f"({', '.join(self.config.allowed_host_suffixes)}). Refused before "
                "sending so credentials never leave for an untrusted host.",
                operation_id=operation_id, endpoint=path, retryable=False,
            )
        if creds_override is not None:
            creds, err = creds_override, None
        else:
            creds, err = self._creds_or_error()
        if err:
            return err
        headers = {
            "User-Agent": self.config.user_agent,
            "Accept": "application/json",
        }
        if self.config.is_oauth:
            # OAuth services: obtain/refresh a cached bearer and send it.
            # build_headers is intentionally NOT used for auth here.
            token, terr = await self._ensure_token(creds or {})
            if terr:
                return terr
            headers["Authorization"] = f"Bearer {token}"
            headers["Content-Type"] = "application/json"
        else:
            # Static-header services (WB, Ozon Seller): unchanged behaviour.
            headers.update(self.config.build_headers(creds or {}))
        url = self._url(host, path)

        attempt = 0
        while True:
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.request(
                        method.upper(),
                        url,
                        params=query or None,
                        json=json_body if json_body is not None else None,
                        headers=headers,
                    )
            except Exception as exc:  # noqa: BLE001 - mapped to envelope
                # Connection-phase failures (never reached the server) are safe to
                # retry for any verb. A read/write-phase timeout may have already
                # been processed server-side, so only auto-retry SAFE verbs — never
                # silently repeat a POST/PATCH (would double-create supplies etc.).
                connect_phase = isinstance(
                    exc, (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout))
                read_phase = isinstance(exc, (httpx.ReadTimeout, httpx.WriteTimeout))
                safe_verb = method.upper() in ("GET", "HEAD")
                if attempt < MAX_RETRIES and (connect_phase or (read_phase and safe_verb)):
                    await asyncio.sleep(BACKOFF_BASE * (2**attempt))
                    attempt += 1
                    continue
                return error_from_exception(
                    exc, operation_id=operation_id, endpoint=path
                )

            # An expired/revoked bearer: drop it so the next call refreshes.
            if resp.status_code == 401 and self.config.is_oauth:
                self._invalidate_token(creds or {})

            if resp.status_code == 429 and attempt < MAX_RETRIES:
                retry_after = _parse_retry_after(resp.headers.get("Retry-After"))
                delay = retry_after if retry_after is not None else BACKOFF_BASE * (2**attempt)
                await asyncio.sleep(min(delay, 60.0))
                attempt += 1
                continue

            if resp.is_success:
                return {"ok": True, "status": resp.status_code, "data": _parse_body(resp)}

            etype, retryable = classify_status(resp.status_code)
            msg = (f"{self.config.name.upper()} API returned {resp.status_code}: "
                   f"{_short_body(resp)}")
            if etype == "auth":
                msg += (f" — the key may be expired or revoked. Rotate it: "
                        f"{self.config.name}_set_key (chat) or re-run the installer.")
            return make_error(
                etype,
                msg,
                code=resp.status_code,
                operation_id=operation_id,
                endpoint=path,
                retryable=retryable,
                retry_after_seconds=_parse_retry_after(resp.headers.get("Retry-After")),
                details=_capped_details(resp),
            )

    async def call_spec(
        self,
        spec: EndpointSpec,
        *,
        path_values: Optional[dict[str, Any]] = None,
        query: Optional[dict[str, Any]] = None,
        json_body: Optional[Any] = None,
        creds_override: Optional[dict[str, str]] = None,
    ) -> dict:
        try:
            path = spec.render_path(path_values or {})
        except KeyError as missing:
            return make_error(
                "invalid_params",
                f"Missing path parameter '{missing.args[0]}' for {spec.operation_id}. "
                f"Path template: {spec.path}",
                operation_id=spec.operation_id,
                endpoint=spec.path,
            )
        return await self.request(
            spec.method,
            spec.host,
            path,
            query=query,
            json_body=json_body,
            operation_id=spec.operation_id,
            creds_override=creds_override,
        )


def _parse_body(resp: httpx.Response) -> Any:
    ctype = resp.headers.get("Content-Type", "")
    if "application/json" in ctype:
        try:
            return resp.json()
        except Exception:  # noqa: BLE001
            return resp.text
    if ctype.startswith(("image/", "application/pdf")):
        return {"_binary": True, "content_type": ctype, "bytes": len(resp.content)}
    return resp.text


def _short_body(resp: httpx.Response, limit: int = 300) -> str:
    body = _parse_body(resp)
    s = body if isinstance(body, str) else str(body)
    return s[:limit]


def _capped_details(resp: httpx.Response, limit: int = 2000) -> Any:
    """Error details for the envelope, bounded so a giant HTML error page can't
    flood the agent's context. Structured JSON bodies are usually small and pass
    through unchanged; long text is truncated with a marker."""
    body = _parse_body(resp)
    if isinstance(body, str) and len(body) > limit:
        return body[:limit] + f"... [truncated {len(body) - limit} chars]"
    return body
