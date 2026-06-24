"""Scan MCP config files for safety risks (secrets in plaintext, curl|bash,
unpinned npx/uvx, over-privileged scopes, tokens without rotation metadata,
mutable docker tags, missing audit logging).

Vendored verbatim from letya999/ai-repo-safety-skill so the check runs without
installing that package. Relevant to this repo because we ship a `.mcp.json`.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

RISKY_NAMES = [".mcp.json", "claude_desktop_config.json"]
RISKY_COMMAND_PATTERNS = [
    re.compile(r"curl\s+.*\|\s*(bash|sh)", re.I),
    re.compile(r"wget\s+.*\|\s*(bash|sh)", re.I),
    re.compile(r"powershell.*(iex|invoke-expression)", re.I),
    re.compile(r"python\s+-c\s+", re.I),
    re.compile(r"node\s+-e\s+", re.I),
]
SECRET_LIKE = re.compile(r"(?i)(token|secret|password|api[_-]?key)\s*[:=]\s*['\"]?[A-Za-z0-9_\-/.=]{12,}")
EXPIRY_KEYS = {"expires", "expires_at", "expiresAt", "expiry", "rotation", "rotates_at", "rotatesAt", "ttl"}
WRITE_SCOPE_RE = re.compile(r"(?i)\b(write|delete|admin|full|all|\*)\b")
DOCKER_LATEST_RE = re.compile(r"(?i)\bdocker://[^\s\"']+:latest\b")


def _walk(node: Any):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)


def _flatten_scopes(node: Any) -> list[str]:
    scopes: list[str] = []
    if isinstance(node, str):
        scopes.append(node)
    elif isinstance(node, list):
        for item in node:
            if isinstance(item, str):
                scopes.append(item)
    return scopes


def _has_expiry_metadata(obj: dict[str, Any]) -> bool:
    return any(key in obj for key in EXPIRY_KEYS)


def _extract_command(obj: dict[str, Any]) -> str:
    for key in ("command", "cmd"):
        value = obj.get(key)
        if isinstance(value, str):
            return value
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            return " ".join(value)
    return ""


def _command_uses_unpinned_npx(command: str) -> bool:
    parts = command.strip().split()
    if len(parts) < 2 or parts[0].lower() != "npx":
        return False
    package = parts[1]
    return "@" not in package[1:]


def _command_uses_unpinned_uvx(command: str) -> bool:
    parts = command.strip().split()
    if len(parts) < 2 or parts[0].lower() != "uvx":
        return False
    package = parts[1]
    return "==" not in package


def _has_audit_logging_hint(obj: dict[str, Any]) -> bool:
    for key, value in obj.items():
        key_lower = str(key).lower()
        if "audit" in key_lower or "log" in key_lower:
            return True
        if isinstance(value, str):
            lower = value.lower()
            if "--audit" in lower or "audit-log" in lower or "--log" in lower:
                return True
        elif isinstance(value, list) and all(isinstance(item, str) for item in value):
            joined = " ".join(value).lower()
            if "--audit" in joined or "audit-log" in joined or "--log" in joined:
                return True
    return False


def scan_file(path: Path) -> list[str]:
    problems: list[str] = []
    text = path.read_text(encoding="utf-8", errors="replace")

    if SECRET_LIKE.search(text):
        problems.append(f"{path.name}: contains secret-like plaintext")
    for pat in RISKY_COMMAND_PATTERNS:
        if pat.search(text):
            problems.append(f"{path.name}: risky command pattern `{pat.pattern}`")
    if DOCKER_LATEST_RE.search(text):
        problems.append(f"{path.name}: docker image uses mutable `latest` tag")

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return problems

    found_audit_logging = False
    saw_sensitive_mcp_shape = False
    for obj in _walk(payload):
        if not isinstance(obj, dict):
            continue

        if _has_audit_logging_hint(obj):
            found_audit_logging = True

        command = _extract_command(obj)
        if command:
            if _command_uses_unpinned_npx(command):
                problems.append(f"{path.name}: unpinned npx package invocation")
                saw_sensitive_mcp_shape = True
            if _command_uses_unpinned_uvx(command):
                problems.append(f"{path.name}: unpinned uvx package invocation")
                saw_sensitive_mcp_shape = True
            if DOCKER_LATEST_RE.search(command):
                saw_sensitive_mcp_shape = True

        for key in ("scope", "scopes", "permissions"):
            if key not in obj:
                continue
            for scope in _flatten_scopes(obj[key]):
                if WRITE_SCOPE_RE.search(scope):
                    problems.append(f"{path.name}: over-privileged scope `{scope}`")
                    saw_sensitive_mcp_shape = True

        token_like = any(isinstance(obj.get(key), str) and len(obj[key]) >= 12
                         for key in ("token", "secret", "password", "apiKey", "api_key"))
        if token_like:
            saw_sensitive_mcp_shape = True
        if token_like and not _has_expiry_metadata(obj):
            problems.append(f"{path.name}: token-like credential without expiry/rotation metadata")

    if saw_sensitive_mcp_shape and not found_audit_logging:
        problems.append(f"{path.name}: no audit/logging hint found for sensitive MCP operations")

    return problems


def main() -> int:
    problems = []
    for name in RISKY_NAMES:
        path = Path(name)
        if not path.exists():
            continue
        problems.extend(scan_file(path))
    if problems:
        print("[repo-safety] MCP config risks:")
        for p in problems:
            print(f"  - {p}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
