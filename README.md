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

### Workflows — recipes, not just endpoints

`*_list_workflows` / `*_get_workflow` expose curated, step-by-step recipes that
turn raw endpoints into outcomes, each with interpretation guidance and common
mistakes. Ozon: `oos_risk_analysis`, `pricing_analysis`, `unit_economics`,
`catalog_sync`, `content_quality_audit`, `abc_analysis`, `reviews_pulse`. WB:
`sales_pulse`, `stock_health`, `price_audit`, `reorder_planner`, `abc_analysis`,
`reviews_pulse`. Every recipe step is integrity-checked against the catalog.

### Coverage

Catalogs are built schema-driven from the official OpenAPI specs:

| Catalog | File | Endpoints | Sections |
|---|---|---:|---|
| Wildberries | `wb_mcp/endpoints.yaml` | **307** | 70 |
| Ozon Seller | `ozon_mcp/endpoints.yaml` | **441** | 67 |
| Ozon Performance | `ozon_mcp/perf_endpoints.yaml` | **45** | 6 |

A curated, live-verified core has exact pagination/params; the rest are imported
from the specs (paths reliable, HTTP verbs not guaranteed — see caveats below).
`call_raw` reaches anything not catalogued. Ozon Performance is **catalog-only**
today — the perf server is a separate follow-up (see `HANDOFF.md`); `serve.py`
exposes `wb` and `ozon`.

## Safety model

Marketplace keys move prices, stock and money. Every endpoint is classified
`read` / `write` / `destructive`:

- **read** → runs immediately.
- **write** → requires `confirm_write=true`.
- **destructive** → requires `confirm_write=true` **and**
  `i_understand_this_modifies_data=true`.

The gate runs locally; if confirmations are missing, nothing is sent.

## Install & distribution

Full step-by-step for every audience lives in **[QUICKSTART.md](QUICKSTART.md)**.
Three paths, same result — pick by comfort level:

1. **Easiest — ask your AI (no terminal).** Open Claude/Cowork and say
   *"install the WB + Ozon MCP"*; it walks you through the bundled
   `install-skill/`. (Cowork's sandbox can't touch your machine, so the final
   double-click stays with you — the skill just gets you there error-free.)
2. **Download & click.** Grab `marketplace-mcp-v<version>.zip` from
   **[GitHub Releases](https://github.com/<OWNER>/marketplace-mcp/releases)**,
   unzip, double-click `install.command` (macOS) / `install.bat` (Windows),
   paste your keys.
3. **Technical.** `git clone https://github.com/<OWNER>/marketplace-mcp` then
   `python3 install.py --client <your-client>`.

<!-- TODO: create the public repo and replace <OWNER> with the real owner. -->

Get keys: **WB** — seller.wildberries.ru → Settings → Access tokens; **Ozon** —
seller.ozon.ru → Settings → API keys. Maintainers cut a release with
`python3 scripts/package_release.py` (clean, secret-free, versioned zip).

The mechanics below apply to every path.

## Install — works on Windows, macOS, Linux

No `pip install`, no JSON editing. Dependencies install themselves on first
launch (a local virtual environment), so the only thing you provide is your API
keys.

**Double-click (easiest):**
- **macOS** — double-click `install.command`
- **Windows** — double-click `install.bat` (it finds the `py` launcher or
  `python` on PATH; if Python is missing it tells you to install it from
  python.org with "Add to PATH" ticked)
- **Linux** — run `bash install.sh`

**Verify it works** (any OS), after install:

```bash
python serve.py ozon --selfcheck     # -> "OK: ozon ready, 19 tools."
```

The launcher self-installs its dependencies into a local virtual environment on
first run and injects them into the running process — no `os.exec`, so the MCP
stdio handshake is identical and reliable on Windows, macOS and Linux.

**Or one command, any OS:**

```bash
python3 install.py
```

**Four clients via `--client`.** `install.py` targets Claude Desktop, Claude
Code, Codex and OpenCode. Server entries are secret-free (keys go to the cabinet
store); Desktop/OpenCode get their config file written, Claude Code/Codex get
ready-to-paste CLI commands:

```bash
python3 install.py                          # interactive, claude-desktop (default)
python3 install.py --client claude-desktop  # writes claude_desktop_config.json
python3 install.py --client claude-code     # prints `claude mcp add` commands
python3 install.py --client codex           # prints `codex mcp add` commands
python3 install.py --client opencode        # writes ~/.config/opencode/opencode.json
```

(`--claude-code` is still accepted as a shorthand for `--client claude-code`.)

All paths route through `install.py`: it asks for your keys, finds the right
config for your OS, writes both servers, and backs up the old config. Restart
the client — done. `serve.py` then self-bootstraps its virtual environment on
first run.

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

### Credentials & cabinets (multi-shop)

Keys are stored in `~/.marketplace-mcp/cabinets.json` (local, chmod 600, never
in the repo or the Claude config). You can run **several cabinets** — e.g. two
Ozon shops — and switch between them from chat.

- **Wildberries**: a token from seller.wildberries.ru → Settings → Access tokens
  (tick the categories you need). Sent raw in the `Authorization` header.
- **Ozon**: `Client-Id` + `Api-Key` from seller.ozon.ru → Settings → API keys.

Manage cabinets from chat (no file editing):

- `ozon_add_cabinet` / `wb_add_cabinet` — add or update a cabinet, e.g.
  `add_cabinet(name="shop2", credentials={"client_id":"...", "api_key":"..."})`.
- `ozon_use_cabinet(name)` — switch the active cabinet.
- `ozon_list_cabinets` — see configured cabinets and which is active.
- `ozon_remove_cabinet(name)` — delete one.
- `ozon_check_auth` / `wb_check_auth` — show the active cabinet, what's missing,
  and where to get keys.

Add more shops at install time too: re-run `python3 install.py --cabinet shop2`.
An env-only setup still works — environment variables act as a fallback cabinet.

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

## Scripts and growing the catalog

`scripts/`:

- `ingest_specs.py` — build the WB catalog from the official OpenAPI specs.
- `ingest_ozon.py` — build the Ozon Seller catalog from the official specs.
- `sync_swagger.py` — additive, idempotent catalog sync from a local swagger.
- `derive_pagination.py` — infer pagination style for catalog entries.
- `validate_items_path.py` — **live** `items_path` validator/auto-fixer (needs
  cabinet creds; run locally — see `HANDOFF.md`).
- `smoke_mcp.py` — quick MCP smoke check.

`*_call_raw` already reaches **any** endpoint not yet catalogued. To grow the
typed catalog, run the swagger sync **locally** (WB/Ozon hosts block many non-RU
IPs):

```bash
python scripts/sync_swagger.py --spec ozon_seller.json \
    --catalog ozon_mcp/endpoints.yaml --service ozon
```

It's additive and idempotent — your curated safety levels and summaries are
never overwritten.

## Tests

```bash
pip install pytest pytest-asyncio
python -m pytest tests/ -q        # 21 offline tests, no tokens needed
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
- **Imported (spec-derived) endpoints: paths are reliable, HTTP verbs are NOT.**
  A live probe found imported GET-labelled endpoints that are actually POST (405
  Method Not Allowed). Treat imported entries as a discovery map: confirm the
  verb/body in the docs, or call with the correct verb via `call_raw`. The
  live-verified core (WB 7 categories, Ozon 4 sections) and the curated set are
  trustworthy as-is. A full live `items_path` sweep is an open follow-up — see
  `HANDOFF.md`.
- Some WB write verbs (tag update, meta setters, supply deliver) were inferred
  where the docs stripped the verb badge — confirm before automating them.

MIT-style usage; no third-party marketplace code is bundled.
