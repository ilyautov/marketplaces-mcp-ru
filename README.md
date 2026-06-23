# marketplace-mcp

Two MCP servers — **`wb_mcp`** (Wildberries Seller API) and **`ozon_mcp`**
(Ozon Seller API) — built on one shared, schema-driven core. Connect any MCP
client (Cowork, Claude Desktop, Claude Code, Cursor, …) to your marketplace
cabinet.

Own code, best patterns: the architecture borrows the strongest ideas from
mature marketplace MCP servers (schema-driven catalog, safety gating, unified
errors, auto-pagination) without depending on anyone else's library.

## Why this shape

The naive approach — one MCP tool per endpoint — produces 300+ tools an agent
can't reason over. Instead each server ships **8 generic meta-tools** over a
**catalog** of endpoints, plus a few **typed convenience tools** for the
everyday jobs. Full API coverage, small tool surface.

```
your AI agent
      │
      ▼
 8 meta-tools  ──►  catalog (endpoints.yaml)  ──►  shared core
 search/describe/                                  client · safety · errors
 call/call_raw/                                     pagination · registry
 fetch_all/...                                            │
 + typed tools (wb_get_sales, ozon_get_prices, ...)       ▼
                                            Wildberries / Ozon HTTPS API
```

## The tools (identical pattern per server, `wb_`/`ozon_` prefix)

| Tool | Purpose |
|---|---|
| `*_check_auth` | Report whether credentials are set (never echoes secrets) |
| `*_list_sections` | Browse the API by section |
| `*_get_section` | List endpoints in one section |
| `*_search_methods` | Keyword search — **Russian or English** |
| `*_describe_method` | Full spec: method, host, path, scope, safety, rate limit, doc |
| `*_call_method` | Execute any catalog endpoint (safety-gated) |
| `*_call_raw` | Execute ANY path, even outside the catalog (full coverage) |
| `*_fetch_all` | Auto-paginate a read endpoint (offset / last_id / page / WB date cursor) |

Typed convenience tools: `wb_get_sales`, `wb_get_stocks`, `wb_get_new_orders`,
`wb_get_prices`, `wb_set_price`; `ozon_get_products`, `ozon_get_stocks`,
`ozon_get_prices`, `ozon_get_fbs_unfulfilled`, `ozon_set_price`.

## Safety model

Marketplace keys move prices, stock and money. Every endpoint is classified
`read` / `write` / `destructive`:

- **read** → runs immediately.
- **write** → requires `confirm_write=true`.
- **destructive** → requires `confirm_write=true` **and**
  `i_understand_this_modifies_data=true`.

The gate runs locally; if confirmations are missing, nothing is sent.

## Install — works on Windows, macOS, Linux

No `pip install`, no JSON editing. Dependencies install themselves on first
launch (a local virtual environment), so the only thing you provide is your API
keys.

**Double-click (easiest):**
- **macOS** — double-click `install.command`
- **Windows** — double-click `install.bat`
- **Linux** — run `bash install.sh`

**Or one command, any OS:**

```bash
python3 install.py
```

**Or let Claude Code do it for you.** In Claude Code (which runs on your
machine), just ask it to install — it can run `install.py` directly, or use:

```bash
python3 install.py --claude-code        # prints ready `claude mcp add` commands
```

All paths route through `install.py`: it asks for your keys, finds your Claude /
Cowork config for your OS, writes both servers, and backs up the old config.
Restart Claude/Cowork — done. `serve.py` then self-bootstraps its virtual
environment on first run.

> Note: Cowork's own sandbox can't install onto your machine for you (it's an
> isolated Linux container, and typing into your terminal is blocked for safety).
> Use the double-click installer, or Claude Code, which runs locally.

Non-interactive (e.g. scripted):

```bash
python3 install.py --wb-token TOKEN --ozon-client-id ID --ozon-api-key KEY
```

Just want to see the config block without changing anything:

```bash
python3 install.py --print
```

### Credentials (stored only in your local Claude config)

- **Wildberries**: `WB_API_TOKEN` — seller.wildberries.ru → Settings → Access
  tokens (one token, tick the categories you need). Sent in the `Authorization`
  header as the raw value (no `Bearer` prefix).
- **Ozon**: `OZON_CLIENT_ID` + `OZON_API_KEY` — seller.ozon.ru → Settings → API
  keys. Sent as `Client-Id` / `Api-Key` headers.

In chat you can always run `wb_check_auth` / `ozon_check_auth` to see whether
keys are set and where to get them.

### Manual config (if you prefer)

```json
{
  "mcpServers": {
    "wildberries": {
      "command": "python3",
      "args": ["/absolute/path/to/marketplace-mcp/serve.py", "wb"],
      "env": { "WB_API_TOKEN": "your-wb-token" }
    },
    "ozon": {
      "command": "python3",
      "args": ["/absolute/path/to/marketplace-mcp/serve.py", "ozon"],
      "env": { "OZON_CLIENT_ID": "your-client-id", "OZON_API_KEY": "your-api-key" }
    }
  }
}
```

`serve.py` self-bootstraps its venv, so `command` can be any Python 3.10+.

## Coverage and growing the catalog

Each catalog ships ~31 curated, verified endpoints across all major sections.
`*_call_raw` already reaches **any** endpoint not yet catalogued. To grow the
typed catalog toward every method, run the swagger sync **locally** (WB/Ozon
hosts block many non-RU IPs):

```bash
python scripts/sync_swagger.py --spec ozon_seller.json \
    --catalog ozon_mcp/endpoints.yaml --service ozon
```

It's additive and idempotent — your curated safety levels and summaries are
never overwritten.

## Tests

```bash
pip install pytest pytest-asyncio
python -m pytest tests/ -q        # 11 offline tests, no tokens needed
```

## Known caveats (verify against live docs before relying on them)

- **WB `Authorization` header**: docs don't show whether the raw token or a
  `Bearer` prefix is expected. This server sends the raw token (community
  practice). If auth fails, that's the first thing to flip.
- **WB finance host**: `wb_finance_balance` host (`common-api`) is unverified.
- **WB realization report** (`/api/v5/.../reportDetailByPeriod`) was flagged for
  possible deprecation in favour of a new finance POST endpoint — confirm.
- **Ozon versions drift silently** (list v3, attributes v4, prices v5, stocks
  v4/v2). If a call 404s, check the version; `sync_swagger.py` re-aligns paths.
- Some WB write verbs (tag update, meta setters, supply deliver) were inferred
  where the docs stripped the verb badge — confirm before automating them.

MIT-style usage; no third-party marketplace code is bundled.
