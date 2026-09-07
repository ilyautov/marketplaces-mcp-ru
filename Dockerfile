# syntax=docker/dockerfile:1
# marketplaces-mcp-ru as a container: the combined WB + Ozon + Ozon Performance
# server. This is the artifact the official MCP Registry advertises as an OCI
# package (ghcr.io/ilyautov/marketplaces-mcp-ru:<version>).
#
#   docker run -i --rm -e WB_API_TOKEN=... ghcr.io/ilyautov/marketplaces-mcp-ru   # stdio
#   docker run --rm -e WB_API_TOKEN=... ghcr.io/ilyautov/marketplaces-mcp-ru doctor
#   docker run --rm -p 8000:8000 -e MCP_TRANSPORT=http -e MCP_HTTP_HOST=0.0.0.0 \
#       -e OZON_CLIENT_ID=... -e OZON_API_KEY=... ghcr.io/ilyautov/marketplaces-mcp-ru
#
# Pure-Python dependencies only, so a single slim stage is enough; the source
# tree is removed after the install so the image carries the installed package
# and nothing else. Pinned to a Python minor on purpose.
FROM python:3.12-slim

# Ownership marker the official MCP Registry checks for OCI packages: it must
# equal server.json's "name".
LABEL io.modelcontextprotocol.server.name="io.github.ilyautov/marketplaces-mcp-ru" \
      org.opencontainers.image.title="marketplaces-mcp-ru" \
      org.opencontainers.image.description="Wildberries & Ozon Seller APIs in your AI assistant — schema-driven, safety-gated MCP server" \
      org.opencontainers.image.source="https://github.com/ilyautov/marketplaces-mcp-ru" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # Cabinet store (keys saved from chat via *_add_cabinet). Mount a volume
    # here to keep them across container restarts; env vars work without it.
    MARKETPLACE_MCP_HOME=/data

COPY pyproject.toml MANIFEST.in README.md LICENSE /src/
COPY core/ /src/core/
COPY wb_mcp/ /src/wb_mcp/
COPY ozon_mcp/ /src/ozon_mcp/
COPY ozon_perf_mcp/ /src/ozon_perf_mcp/

RUN pip install /src \
    && rm -rf /src /root/.cache \
    && useradd --create-home --uid 1000 mcp \
    && mkdir -p /data && chown mcp:mcp /data

USER mcp
VOLUME ["/data"]
# Only used with MCP_TRANSPORT=http; stdio mode opens no port.
EXPOSE 8000

# The registry package runs the combined server over stdio. `doctor` and the
# per-service entry points are one argument / --entrypoint away.
ENTRYPOINT ["marketplaces-mcp-ru"]
