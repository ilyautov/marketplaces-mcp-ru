# Install guide for AI agents (Cline, Claude Code, Cursor and friends)

This file exists so an agent can set the server up from the README alone.
Everything here is also in `README.md` / `QUICKSTART.md`; this is the short path.

## What it is

`marketplaces-mcp-ru` is a Python MCP server that connects an assistant to the
**seller** accounts of Wildberries and Ozon through their official Seller APIs
(sales, stocks, prices, finance, reviews). It needs the seller's own API keys;
without keys it starts but every call reports `missing credentials`.

## Fastest install (no clone)

No prerequisites with npm: the launcher fetches `uv` and the pinned PyPI version itself. Add an MCP server entry:

```json
{
  "mcpServers": {
    "marketplaces-ru": {
      "command": "npx",
      "args": ["-y", "marketplaces-mcp-ru"],
      "env": {
        "WB_API_TOKEN": "<wildberries seller token, optional>",
        "OZON_CLIENT_ID": "<ozon client id, optional>",
        "OZON_API_KEY": "<ozon api key, optional>",
        "YANDEX_MARKET_API_KEY": "<yandex market api key, optional>",
        "AVITO_CLIENT_ID": "<avito client id, optional>",
        "AVITO_CLIENT_SECRET": "<avito client secret, optional>"
      }
    }
  }
}
```

Leave out the variables for marketplaces the user does not sell on. Ozon
Performance (ads) is optional: `OZON_PERF_CLIENT_ID` + `OZON_PERF_CLIENT_SECRET`.
Yandex Market: `YANDEX_MARKET_API_KEY` (partner.market.yandex.ru → Settings → API access).
Avito: `AVITO_CLIENT_ID` + `AVITO_CLIENT_SECRET` (avito.ru → For business → Integrations → API).

Docker alternative (same env vars):

```json
{
  "mcpServers": {
    "marketplaces-ru": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "-e", "WB_API_TOKEN", "-e", "OZON_CLIENT_ID", "-e", "OZON_API_KEY",
               "ghcr.io/ilyautov/marketplaces-mcp-ru:latest"],
      "env": { "WB_API_TOKEN": "...", "OZON_CLIENT_ID": "...", "OZON_API_KEY": "..." }
    }
  }
}
```

## From a clone

```bash
git clone https://github.com/ilyautov/marketplaces-mcp-ru
cd marketplaces-mcp-ru
python3 install.py --client claude-code    # or: claude-desktop | codex | opencode
```

`install.py` copies the app to `~/.marketplace-mcp/app`, writes the client
config (or prints the `mcp add` command), and stores keys in
`~/.marketplace-mcp/cabinets.json` (chmod 600). `serve.py` creates its own
`.venv` on first run; no `pip install` step.

## Verify

```bash
npx -y marketplaces-mcp-ru doctor          # tools mounted, catalogs, keys found?
npx -y marketplaces-mcp-ru doctor --live   # plus one real read call per marketplace
# same with uv installed: uvx marketplaces-mcp-ru doctor [--live]
```

Exit code 0 means every configured marketplace answered. Exit code 1 with
"no credentials" means keys are missing — ask the user for them, do not guess.

## Where the user gets keys

- Wildberries: seller.wildberries.ru → Settings → API access (one token, tick the categories).
- Ozon: seller.ozon.ru → Settings → API keys (Client-Id + Api-Key).

Keys never go into the repo, the client config beyond `env`, or the chat log.
Writes (price / stock changes) are gated: the tools require
`confirm_write=true`, destructive ones additionally `i_understand_this_modifies_data=true`.
