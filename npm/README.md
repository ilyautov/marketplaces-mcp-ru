# marketplaces-mcp-ru (npm launcher)

MCP server for **Wildberries, Ozon, Yandex Market and Avito** seller APIs: 1022 schema-driven methods, Russian-language search, a safety gate on every write. This npm package is a thin launcher: the server is Python and lives on PyPI as `marketplaces-mcp-ru`; `npx` fetches `uv` once (verified download from the official uv release) and runs the pinned PyPI version. No Python setup on your side.

```json
{
  "mcpServers": {
    "marketplaces-ru": {
      "command": "npx",
      "args": ["-y", "marketplaces-mcp-ru"],
      "env": {
        "WB_API_TOKEN": "...",
        "OZON_CLIENT_ID": "...",
        "OZON_API_KEY": "...",
        "YANDEX_MARKET_API_KEY": "...",
        "AVITO_CLIENT_ID": "...",
        "AVITO_CLIENT_SECRET": "..."
      }
    }
  }
}
```

Set only the keys for the marketplaces you sell on. Check the install:

```bash
npx -y marketplaces-mcp-ru doctor          # tools, catalogs, which keys were found
npx -y marketplaces-mcp-ru doctor --live   # plus one real read call per marketplace
```

Environment knobs: `MARKETPLACES_MCP_RU_VERSION` (PyPI version to run, default = this package's version), `MARKETPLACES_MCP_RU_HOME` (cache dir, default `~/.cache/marketplaces-mcp-ru`), `MARKETPLACES_MCP_RU_NO_DOWNLOAD=1` (never download uv; fall back to a local Python ≥ 3.10).

Docs, one-click installs for Claude Desktop / VS Code / Cursor, Docker image and the full tool list: <https://github.com/ilyautov/marketplaces-mcp-ru>.

---

MCP-сервер для кабинетов **Wildberries, Ozon, Яндекс Маркета и Авито**: продажи, заказы, остатки, цены, отзывы через Seller API. Этот npm-пакет — только запускалка: сервер написан на Python и лежит на PyPI, `npx` сам скачает `uv` и запустит нужную версию. Python ставить не нужно. Подробности и другие способы установки — в репозитории по ссылке выше.
