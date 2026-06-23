"""Unified error envelope shared by every tool of every marketplace server.

A single, stable shape lets an agent branch on `error_type` and `retryable`
without parsing free-form strings. Mirrors the best pattern observed in mature
marketplace MCP servers.
"""
from __future__ import annotations

from typing import Any, Optional

import httpx

# Canonical error types. Keep this list short and stable — agents branch on it.
ERROR_TYPES = (
    "auth",            # missing/invalid credentials
    "forbidden",       # authenticated but not allowed (wrong token scope / tier)
    "not_found",       # resource or endpoint does not exist
    "invalid_params",  # request rejected as malformed (4xx other than above)
    "rate_limit",      # 429 — retry with backoff
    "conflict",        # 409
    "server_error",    # 5xx on the marketplace side
    "timeout",         # network timeout
    "network",         # connection failure
    "safety_gate",     # blocked locally before the call left the machine
    "unknown",
)


def make_error(
    error_type: str,
    message: str,
    *,
    code: Optional[int] = None,
    operation_id: Optional[str] = None,
    endpoint: Optional[str] = None,
    retryable: bool = False,
    retry_after_seconds: Optional[float] = None,
    details: Any = None,
) -> dict:
    """Build the canonical error envelope.

    Returns a dict (the calling tool serializes it to JSON). `http_call_skipped`
    is implied for safety_gate via retryable=False + no code.
    """
    if error_type not in ERROR_TYPES:
        error_type = "unknown"
    env: dict[str, Any] = {
        "ok": False,
        "error": error_type,
        "error_type": error_type,
        "message": message,
        "retryable": retryable,
    }
    if code is not None:
        env["code"] = code
    if operation_id:
        env["operation_id"] = operation_id
    if endpoint:
        env["endpoint"] = endpoint
    if retry_after_seconds is not None:
        env["retry_after_seconds"] = retry_after_seconds
    if details is not None:
        env["details"] = details
    return env


def classify_status(status: int) -> tuple[str, bool]:
    """Map an HTTP status code to (error_type, retryable)."""
    if status == 401:
        return "auth", False
    if status == 403:
        return "forbidden", False
    if status == 404:
        return "not_found", False
    if status == 409:
        return "conflict", False
    if status == 429:
        return "rate_limit", True
    if 500 <= status < 600:
        return "server_error", True
    if 400 <= status < 500:
        return "invalid_params", False
    return "unknown", False


def error_from_exception(
    exc: Exception,
    *,
    operation_id: Optional[str] = None,
    endpoint: Optional[str] = None,
) -> dict:
    """Convert a transport-level exception into the canonical envelope."""
    if isinstance(exc, httpx.TimeoutException):
        return make_error(
            "timeout",
            "Request timed out. The marketplace did not respond in time; retry shortly.",
            operation_id=operation_id,
            endpoint=endpoint,
            retryable=True,
        )
    if isinstance(exc, httpx.ConnectError):
        return make_error(
            "network",
            "Could not connect to the marketplace host. Check network/region access "
            "(WB and Ozon block many non-RU IPs).",
            operation_id=operation_id,
            endpoint=endpoint,
            retryable=True,
        )
    return make_error(
        "unknown",
        f"Unexpected error: {type(exc).__name__}: {exc}",
        operation_id=operation_id,
        endpoint=endpoint,
    )
