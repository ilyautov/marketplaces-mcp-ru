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
import os
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

import httpx

from .errors import classify_status, error_from_exception, make_error
from .registry import EndpointSpec

DEFAULT_TIMEOUT = 30.0
MAX_RETRIES = 4
BACKOFF_BASE = 1.5  # seconds; * 2**attempt


@dataclass
class ServiceConfig:
    """Per-service wiring. Keeps all WB/Ozon specifics out of the engine."""
    name: str                                   # "wb" | "ozon"
    scheme: str                                 # "https"
    required_env: list[str]                     # env var names that must be set
    # creds(env) -> dict of resolved credentials
    load_creds: Callable[[dict[str, str]], dict[str, str]]
    # headers(creds) -> dict of HTTP headers (auth)
    build_headers: Callable[[dict[str, str]], dict[str, str]]
    user_agent: str = "marketplace-mcp/0.1 (+https://github.com/)"

    def missing_env(self) -> list[str]:
        return [k for k in self.required_env if not os.environ.get(k)]


def _parse_retry_after(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    try:
        return float(value)  # delta-seconds
    except ValueError:
        # HTTP-date form
        dt = email.utils.parsedate_to_datetime(value)
        if dt is None:
            return None
        return max(0.0, dt.timestamp() - time.time())


class MarketplaceClient:
    def __init__(self, config: ServiceConfig):
        self.config = config

    # --- credential handling -------------------------------------------------
    def _creds_or_error(self) -> tuple[Optional[dict[str, str]], Optional[dict]]:
        missing = self.config.missing_env()
        if missing:
            return None, make_error(
                "auth",
                f"Missing credentials. Set environment variable(s): {', '.join(missing)}. "
                "They are read from the environment only, never passed as tool arguments.",
                retryable=False,
            )
        creds = self.config.load_creds(dict(os.environ))
        return creds, None

    def _url(self, host: str, path: str) -> str:
        host = host.replace("https://", "").replace("http://", "").strip("/")
        return f"{self.config.scheme}://{host}{path}"

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
    ) -> dict:
        """Execute one HTTP request with 429 backoff. Returns a dict:
        success -> {"ok": True, "status": int, "data": <parsed json|text>}
        failure -> canonical error envelope (ok=False).
        """
        creds, err = self._creds_or_error()
        if err:
            return err
        headers = {
            "User-Agent": self.config.user_agent,
            "Accept": "application/json",
            **self.config.build_headers(creds or {}),
        }
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
                if attempt < MAX_RETRIES and isinstance(
                    exc, (httpx.TimeoutException, httpx.ConnectError)
                ):
                    await asyncio.sleep(BACKOFF_BASE * (2**attempt))
                    attempt += 1
                    continue
                return error_from_exception(
                    exc, operation_id=operation_id, endpoint=path
                )

            if resp.status_code == 429 and attempt < MAX_RETRIES:
                retry_after = _parse_retry_after(resp.headers.get("Retry-After"))
                delay = retry_after if retry_after is not None else BACKOFF_BASE * (2**attempt)
                await asyncio.sleep(min(delay, 60.0))
                attempt += 1
                continue

            if resp.is_success:
                return {"ok": True, "status": resp.status_code, "data": _parse_body(resp)}

            etype, retryable = classify_status(resp.status_code)
            return make_error(
                etype,
                f"{self.config.name.upper()} API returned {resp.status_code}: "
                f"{_short_body(resp)}",
                code=resp.status_code,
                operation_id=operation_id,
                endpoint=path,
                retryable=retryable,
                retry_after_seconds=_parse_retry_after(resp.headers.get("Retry-After")),
                details=_parse_body(resp),
            )

    async def call_spec(
        self,
        spec: EndpointSpec,
        *,
        path_values: Optional[dict[str, Any]] = None,
        query: Optional[dict[str, Any]] = None,
        json_body: Optional[Any] = None,
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
