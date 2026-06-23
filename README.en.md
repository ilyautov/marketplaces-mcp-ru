# marketplaces-mcp-ru: AI access to Wildberries & Ozon seller accounts for Claude Code, Cursor, Codex & Cowork

> [Русская версия](README.md)

> **You sell on WB and Ozon — give your AI direct access to both seller accounts.**
> Two MCP servers over the Wildberries and Ozon Seller APIs: **793 methods**
> (sales, stock, prices, finance, reviews, supplies, ads), built schema-driven
> from the official OpenAPI specs. Numbers come from the **real API**, not made
> up by the model. A **safety gate** prevents accidentally changing a price or a
> stock level. Auto-pagination, multi-account, Russian-language search. For
> Claude Code, Cursor, Codex, Cowork and Claude Desktop.

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

## Why

You sell on two marketplaces at once, but the data lives in two separate
dashboards. Sales, stock, prices, finance, reviews — all by hand, through two
browsers. A generic AI assistant is usually useless here: it either drives a
browser and trips over a captcha, or invents confident-sounding numbers.

`marketplaces-mcp-ru` comes from the other side — it gives the AI agent **direct
access to the Seller API of both accounts**:

- **Numbers from the real API, not from the model's head.** Sales, stock,
  margin, finance reports — that's the actual Wildberries/Ozon response, with
  source and fields, not a plausible fabrication.
- **A safety gate on everything that touches money.** Every method is tagged
  `read` / `write` / `destructive`; reads run immediately, but changing a price
  or stock requires explicit confirmation.
- **No browser, no captcha.** Direct HTTPS calls with your account token.

Just ask in plain words: "show this week's sales on both", "what should I
reorder", "compare my prices to the market" — the agent picks the method or a
ready-made workflow and walks you through it.

> ⚠️ **alpha.** Helpful for a seller's day-to-day, but it's a tool, not a
> replacement for an analyst. The curated core is battle-tested on real
> accounts; methods imported from specs are a reconnaissance map (paths are
> reliable, confirm HTTP verbs against the docs).

## What's inside

Not "one tool per endpoint" (that's 300+ tools the agent drowns in), but **8
generic meta-tools over a catalog** — full API coverage with a tiny surface.

| Catalog | File | Methods | Sections |
|---|---|---:|---|
| Wildberries | `wb_mcp/endpoints.yaml` | **307** | 70 |
| Ozon Seller | `ozon_mcp/endpoints.yaml` | **441** | 67 |
| Ozon Performance (ads) | `ozon_mcp/perf_endpoints.yaml` | **45** | 6 |

**Meta-tools** (same set on both servers, prefixed `wb_` / `ozon_`):
`*_check_auth`, `*_search_methods` (search in Russian or English),
`*_describe_method`, `*_call_method` (through the safety gate), `*_call_raw`
(any path, even outside the catalog — 100% coverage), `*_fetch_all`
(auto-pagination). Plus typed convenience tools (`wb_get_sales`,
`ozon_get_prices`, …) and account tools.

Selfcheck reports 19 tools for `wb`, 19 for `ozon`, 14 for `ozon-perf`.

## Install

1. **Easiest — ask your AI (no terminal).** Open Claude / Cowork and say
   "install the WB + Ozon MCP" — the agent walks the bundled `install-skill/`.
2. **Download and click.** Grab `marketplaces-mcp-ru-v<version>.zip` from
   [GitHub Releases](https://github.com/ilyautov/marketplaces-mcp-ru/releases),
   unzip, double-click `install.command` (macOS) / `install.bat` (Windows),
   paste your keys. On Windows the installer can fetch Python via winget if it's
   missing.
3. **Manual.** `python3 install.py --client claude-desktop`
   (or `claude-code` / `codex` / `opencode`).

You need Python 3.10+. Dependencies install themselves into a local `.venv` on
first run.

**Verify:** `python3 serve.py ozon --selfcheck`

## Security

Keys are stored locally only, in `~/.marketplace-mcp/cabinets.json` (`chmod
600`), never written to the client config or printed into the chat. See
[SECURITY.md](SECURITY.md). To report a vulnerability, email
**ilyautov@gmail.com** (subject `SECURITY: marketplaces-mcp-ru`) — please don't
open a public issue.

## License

MIT. Free and open source. Found a bug? Open an
[issue](https://github.com/ilyautov/marketplaces-mcp-ru/issues) — but never put
real keys or account data in it.
