"""Transport selection: stdio by default, Streamable HTTP only when asked.

Uses a stand-in for FastMCP so the test never opens a port. The stand-in
mirrors the two things ``core.transport`` touches: ``.settings`` (host, port,
transport_security) and ``.run(transport=...)``.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core import transport  # noqa: E402


class FakeMCP:
    def __init__(self, host="127.0.0.1", port=8000):
        from mcp.server.transport_security import TransportSecuritySettings

        # What FastMCP builds for its default loopback host.
        sec = TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=["127.0.0.1:*", "localhost:*", "[::1]:*"],
        )
        self.settings = SimpleNamespace(host=host, port=port, transport_security=sec)
        self.calls: list[dict] = []

    def run(self, **kwargs):
        self.calls.append(kwargs)


def test_default_is_stdio():
    assert transport.transport_from_env({}) == "stdio"
    m = FakeMCP()
    transport.run(m, env={})
    assert m.calls == [{}]  # plain mcp.run(), stdio


@pytest.mark.parametrize("value", ["http", "HTTP", "streamable-http", "streamable_http"])
def test_http_aliases(value):
    assert transport.transport_from_env({"MCP_TRANSPORT": value}) == "http"


def test_unknown_transport_is_rejected():
    with pytest.raises(ValueError, match="MCP_TRANSPORT"):
        transport.transport_from_env({"MCP_TRANSPORT": "sse"})


def test_http_runs_streamable_http_on_loopback_and_keeps_guard():
    m = FakeMCP()
    transport.run(m, env={"MCP_TRANSPORT": "http", "MCP_HTTP_PORT": "9010"})
    assert m.calls == [{"transport": "streamable-http"}]
    assert (m.settings.host, m.settings.port) == ("127.0.0.1", 9010)
    # loopback keeps the SDK's localhost allowlist
    assert m.settings.transport_security is not None
    assert m.settings.transport_security.enable_dns_rebinding_protection


def test_http_on_any_interface_drops_stale_localhost_allowlist(capsys):
    m = FakeMCP()
    transport.run(m, env={"MCP_TRANSPORT": "http", "MCP_HTTP_HOST": "0.0.0.0"})
    assert m.settings.host == "0.0.0.0"
    assert m.settings.transport_security is None
    assert "MCP_HTTP_ALLOWED_HOSTS" in capsys.readouterr().err


def test_http_allowed_hosts_enables_guard_with_operator_list():
    m = FakeMCP()
    transport.run(m, env={
        "MCP_TRANSPORT": "http", "MCP_HTTP_HOST": "0.0.0.0",
        "MCP_HTTP_ALLOWED_HOSTS": "mcp.example.com:*, 10.0.0.5:8000",
    })
    sec = m.settings.transport_security
    assert sec is not None and sec.enable_dns_rebinding_protection
    assert sec.allowed_hosts == ["mcp.example.com:*", "10.0.0.5:8000"]


@pytest.mark.parametrize("port", ["0", "70000", "abc"])
def test_bad_port_is_rejected(port):
    with pytest.raises(ValueError):
        transport.configure_http(FakeMCP(), env={"MCP_HTTP_PORT": port})
