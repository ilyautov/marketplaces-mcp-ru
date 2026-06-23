"""Shared core for marketplace MCP servers (Wildberries, Ozon).

Service-agnostic building blocks:
- errors:   unified error envelope
- safety:   read/write/destructive gating
- registry: schema-driven endpoint catalog (loaded from YAML)
- client:   async HTTP client with auth, 429 backoff, pagination
"""
