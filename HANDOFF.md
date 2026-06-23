# HANDOFF — marketplace-mcp

Two MCP servers (`wb_mcp`, `ozon_mcp`) over one schema-driven core. This is the
practical state-of-play and the exact commands to close the open follow-ups.

## Current state (verified by reading the repo, not assumed)

| Catalog | File | Endpoints | Sections | read / write / destructive |
|---|---|---:|---:|---|
| Wildberries | `wb_mcp/endpoints.yaml` | **307** | 70 | 191 / 104 / 12 |
| Ozon Seller | `ozon_mcp/endpoints.yaml` | **441** | 67 | 115 / 315 / 11 |
| Ozon Performance | `ozon_mcp/perf_endpoints.yaml` | **45** | 6 | 30 / 13 / 2 |

> Counts reproduced with:
> `python3 -c "import sys;sys.path.insert(0,'.');from core.registry import Catalog;print(len(Catalog.from_yaml('wb_mcp/endpoints.yaml').all()),len(Catalog.from_yaml('ozon_mcp/endpoints.yaml').all()))"`
> -> `307 441`. The perf server **is now wired** (`serve.py` exposes `wb`, `ozon`,
> `ozon-perf`), but its OAuth token-endpoint contract is **unverified live** (no
> perf creds yet) — see follow-up (b).

**Servers:** `serve.py wb --selfcheck` and `serve.py ozon --selfcheck` each report
**19 tools** (8 meta-tools + typed convenience tools + cabinet/workflow tools);
`serve.py ozon-perf --selfcheck` reports **14 tools** (meta-tools + perf-specific
convenience tools). All three verified via Claude Code (`--selfcheck` exits 0).

**Tests:** `21 passed` offline, in a clean env (no tokens). Command:
`env -u OZON_CLIENT_ID -u OZON_API_KEY -u WB_API_TOKEN python3 -m pytest tests/ -q`.
(17 in `test_mock.py`; 4 in `test_perf_oauth.py`, added by the perf agent — the
perf OAuth flow is already being built in parallel.)

**Verified live** (real cabinets, earlier sessions — keys NOT stored in repo):
- WB: 7 token categories probed; read endpoints return data; raw `Authorization`
  header (no `Bearer`) confirmed working.
- Ozon Seller: 4 sections probed live; cursor/last_id pagination styles confirmed;
  `items_path` fixed for the live-checked core.
- Safety gate honoured end-to-end: **0 mutations** during read probes; `write`
  needs `confirm_write=true`, `destructive` needs the extra
  `i_understand_this_modifies_data=true`.

**Auth recap:** WB -> raw token in `Authorization` (no `Bearer`). Ozon Seller ->
`Client-Id` + `Api-Key` headers. Keys live in `~/.marketplace-mcp/cabinets.json`
(chmod 600), never in the repo.

## Open follow-ups (with exact commands)

### (a) Full `items_path` sweep — run locally
Imported endpoints carry `items_path` from the spec; only the live-checked core
is confirmed against real response shapes. Run the live validator locally — no
45s sandbox limit, fresh rate budget. It throttles, skips non-200s, and
auto-fixes unambiguous single-array misses.

```bash
export OZON_CLIENT_ID=...  OZON_API_KEY=...
export WB_API_TOKEN=...
python3 scripts/validate_items_path.py ozon    # sweeps ozon_mcp/endpoints.yaml
python3 scripts/validate_items_path.py wb      # sweeps wb_mcp/endpoints.yaml
```
Credentials are read from env (`OZON_CLIENT_ID`/`OZON_API_KEY`, `WB_API_TOKEN`).
The script rewrites `items_path` in place where the live response disagrees with
the spec; review the diff before committing.

### (b) Ozon Performance OAuth — needs perf creds + token-endpoint contract
`perf_endpoints.yaml` is a complete catalog (45 methods) but no perf server runs
yet. Performance API uses a **separate** Client-Id/Client-Secret and an OAuth
token endpoint (not the Seller `Client-Id`/`Api-Key` header). Before wiring the
server:
1. Obtain Performance API credentials (seller.ozon.ru -> Performance -> API).
2. Confirm the token endpoint contract (URL, grant type, token TTL, header
   format for the bearer token on subsequent calls) against live docs.
3. Then add a `ServiceConfig` for perf (separate auth flow) and register it in
   `serve.py` SERVICES.

### (c) Rotate API keys — they were used in a working session
WB token and Ozon Seller keys were exercised against live cabinets. Treat them
as exposed: reissue WB token (seller.wildberries.ru -> Settings -> Access tokens)
and Ozon keys (seller.ozon.ru -> Settings -> API keys), then re-save via
`python3 install.py` (or `*_add_cabinet` from chat). Old keys: revoke.

## Install per client

`install.py` targets four clients via `--client`. Secret-free server entries go
to the client config; keys go to the cabinet store.

```bash
python3 install.py                                # interactive, claude-desktop (default)
python3 install.py --client claude-desktop        # writes claude_desktop_config.json
python3 install.py --client claude-code           # prints `claude mcp add` commands
python3 install.py --client codex                 # prints `codex mcp add` commands
python3 install.py --client opencode              # writes ~/.config/opencode/opencode.json
python3 install.py --print                        # show config block, change nothing
python3 install.py --wb-token T --ozon-client-id ID --ozon-api-key KEY   # non-interactive
python3 install.py --cabinet shop2                # add a second shop
```
Double-click installers also exist: `install.command` (macOS), `install.bat`
(Windows), `install.sh` (Linux). Cowork's own sandbox can't install onto the
host — use the double-click route or Claude Code (runs locally).

## Scripts (`scripts/`)
- `ingest_specs.py` — build WB catalog from official OpenAPI specs.
- `ingest_ozon.py` — build Ozon Seller catalog from official specs.
- `sync_swagger.py` — additive, idempotent catalog sync from a local swagger.
- `derive_pagination.py` — infer pagination style for catalog entries.
- `validate_items_path.py` — **live** `items_path` validator/auto-fixer (see (a)).
- `smoke_mcp.py` — quick MCP smoke check.

## Caveats still standing
- Imported endpoints: **paths reliable, HTTP verbs not guaranteed** — confirm
  verb/body against docs or use `call_raw` with the correct verb.
- Ozon API versions drift (list v3, attributes v4, prices v5, stocks v4/v2) —
  on 404 check the version.
- WB finance/realization-report hosts flagged for possible deprecation — confirm.
