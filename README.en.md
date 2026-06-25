# marketplaces-mcp-ru — Wildberries & Ozon inside your AI assistant

> 🇷🇺 [Русская версия](README.md)

Connects an AI assistant (Claude, Cursor, Codex, Cowork and others) directly to your Wildberries and Ozon seller accounts. You ask in plain words; the agent pulls sales, stock, prices, finance and reviews straight from the marketplace API instead of inventing numbers.

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

## Why

You sell on two marketplaces, but the data lives in two separate dashboards. Sales, stock, prices, finance, reviews — all by hand, through two browsers, one at a time. A generic AI assistant doesn't help much here: it either drives a browser and trips over a captcha, or names confident-sounding numbers pulled out of thin air.

This project takes a different route — it gives the assistant direct access to the Seller API of both accounts:

- Numbers come from the actual Wildberries/Ozon response, with source and fields. Not a retelling, not a guess.
- Before changing a price or stock level, the agent asks for confirmation. You can't accidentally cut a price threefold.
- No browser, no captcha — calls go directly with your account token.

Just ask in plain words: "show this week's sales on both", "what should I reorder", "compare my prices to the market" — the agent picks the right method or a ready-made workflow and walks you through it.

> ⚠️ alpha. Helpful for a seller's day-to-day, but it's a tool, not a replacement for an analyst. The hand-checked core (sales, stock, prices, finance, reviews) is verified on real accounts; the rest is imported from specs and serves as a reconnaissance map. See [Caveats](#caveats).

## What you can ask

Just type to the agent in plain language:

```
show this week's sales on WB and Ozon and compare them
what should I reorder — compute days of cover from stock and sales
pull the WB realization finance report for last month
which Ozon products have a red price index
collect reviews below 4 stars this week and group complaints by product
run an ABC analysis by revenue and show the tail products
```

Not sure where to start? Say "what can you do with my account". The agent will show ready-made workflows: for Wildberries — sales pulse, stock health, price audit, reorder planner, ABC analysis, reviews summary; for Ozon — out-of-stock risk, pricing analysis, unit economics, catalog sync, content audit, plus the same ABC and reviews. Each workflow is a step-by-step recipe with interpretation and common pitfalls.

## Install

A detailed guide for any audience is in [QUICKSTART.md](QUICKSTART.md). Three ways, one result:

1. **Ask your AI (no terminal).** Open Claude or Cowork and say "install the WB + Ozon MCP". The agent walks the bundled `install-skill/`. In the Cowork sandbox the final click stays with you; in Claude Code it installs fully on its own.
2. **Download and click.** Grab `marketplaces-mcp-ru-v<version>.zip` from [GitHub Releases](https://github.com/ilyautov/marketplaces-mcp-ru/releases), unzip, double-click `install.command` (macOS) / `install.bat` (Windows), paste your keys. On Windows the installer can fetch Python via winget if it's missing.
3. **Terminal.** `git clone https://github.com/ilyautov/marketplaces-mcp-ru`, then `python3 install.py --client <your-client>` (`claude-desktop`, `claude-code`, `codex` or `opencode`).

You need Python 3.10+. Dependencies install themselves into a local `.venv` on first run, so there's no `pip install` or manual JSON editing — all you provide are the keys. Several stores can be connected and switched from chat (`*_add_cabinet` / `*_use_cabinet`).

**Where to get keys.** Wildberries: seller.wildberries.ru → Settings → API access. Ozon: seller.ozon.ru → Settings → API keys. Keys are stored locally in `~/.marketplace-mcp/cabinets.json` (`chmod 600`) and never written to the client config or printed into the chat.

**Verify:** `python3 serve.py ozon --selfcheck`

## Security

An account key moves prices, stock and money, so every method is tagged by risk level up front:

- `read` — runs immediately;
- `write` — requires `confirm_write=true`;
- `destructive` — requires `confirm_write=true` and `i_understand_this_modifies_data=true`.

The check runs locally; nothing leaves without confirmation. A CI test (`test_safety_catalog.py`) guarantees a mutating method can't be tagged `read` — the build fails if a PUT/PATCH/DELETE lands in the catalog as `read`. See [SECURITY.md](SECURITY.md). To report a vulnerability, email **ilyautov@gmail.com** (subject `SECURITY: marketplaces-mcp-ru`) rather than opening a public issue.

## How it works

Under the hood are two MCP servers (Wildberries and Ozon) on a shared core. Instead of "one tool per endpoint" (that's 300+ tools the agent drowns in), there are 8 generic meta-tools over a catalog of methods — full API coverage with a small surface.

Meta-tools are the same on both servers (prefixed `wb_` / `ozon_`): `*_check_auth`, `*_search_methods` (search in Russian or English), `*_describe_method`, `*_call_method` (through the safety gate), `*_call_raw` (any path, even outside the catalog — full coverage), `*_fetch_all` (auto-pagination). Plus typed convenience tools (`wb_get_sales`, `ozon_get_prices`, …) and account tools. Selfcheck reports 19 tools for `wb`, 19 for `ozon`, 14 for `ozon-perf`.

The catalog is built schema-driven from the official OpenAPI specs:

| Catalog | File | Methods | Sections |
|---|---|---:|---|
| Wildberries | `wb_mcp/endpoints.yaml` | 307 | 70 |
| Ozon Seller | `ozon_mcp/endpoints.yaml` | 441 | 67 |
| Ozon Performance (ads) | `ozon_mcp/perf_endpoints.yaml` | 45 | 6 |

The core (sales, stock, prices, finance, reviews) is verified live; the rest is imported from specs, and `call_raw` reaches anything not yet in the catalog.

Tests:

```bash
python3 -m pytest tests/ -q        # 21 offline tests, no tokens needed
```

## FAQ

**Do I need to code?** No. There's an "ask your AI" install and a double-click install. No `pip install`, no JSON editing — dependencies install themselves, you just provide an API key.

**Is it safe? Where do keys go?** The server runs where your agent runs — locally. Keys live in `~/.marketplace-mcp/cabinets.json` (`chmod 600`), never in the repo or the chat. Any change to your account (price, stock) happens only with your confirmation.

**How is this better than scrapers and browser bots?** It's the direct Seller API by token, not page scraping: no captcha, no blocks, structured data — plus protection against accidentally changing a price or stock level.

**Is it free?** Yes, open source under MIT.

## Caveats

Check against the marketplaces' live docs:

- **WB `Authorization`** — the server sends a raw token without a `Bearer` prefix (confirmed in practice). If auth fails, check this first.
- **Methods imported from specs: paths are reliable, HTTP verbs aren't always.** A live probe found methods tagged GET that are actually POST (405). Treat such entries as a reconnaissance map: confirm the verb and body against the docs, or call via `call_raw`. The curated core and the live-verified set are reliable.
- **Ozon drifts across versions** (list v3, attributes v4, prices v5). On a 404, check the version; `ingest_ozon.py` realigns paths.
- **Ozon Performance** is a catalog artifact plus an OAuth wrapper from the docs; the token-endpoint contract isn't verified live yet (needs ad credentials).
- **An account shadows env vars.** The active account in `cabinets.json` takes priority over environment variables. An unexplained 401 or "Client-Id should be positive integer" — check that file first.

## License

MIT. Free and open source. Found a bug? Open an [issue](https://github.com/ilyautov/marketplaces-mcp-ru/issues) — but never put real keys or account data in it.
