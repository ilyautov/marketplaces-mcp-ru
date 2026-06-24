# Terminal-free cabinet & key lifecycle — design

Date: 2026-06-24
Status: approved for implementation
Scope: subproject #7 of the "terminal-free everywhere" north star.

## Goal

A marketplace seller manages their API keys and shops **without a terminal**,
making an informed choice between "safe" and "convenient". Concretely:
- change an expired/leaked key from chat, with explicit consent;
- name cabinets by their real shop name, pulled from the marketplace API;
- get a clear "your key is dead, rotate it" hint when the API rejects auth;
- run several shops (multi-cabinet), already partly supported.

### Out of scope (separate threads, not this plan)
- Local mini-form / `localhost` key capture.
- Proactive "token expires soon" warning (parsing WB-JWT TTL).
- Encryption-at-rest for the store (today: `chmod 600`).
- Natural-language command ergonomics (subproject #8).

## North star: two doors, informed choice

- **Door 1 — at install (default, safe).** `install.py` / double-click. The key
  never enters the chat transcript. Already exists; we only add a multi-shop loop.
- **Door 2 — from chat (convenient, consented).** A dedicated tool puts the key
  in, but only after the user explicitly acknowledges the key will land in the
  chat history. The secret goes to the provider's transcript once — acceptable
  for scoped, easily-rotated marketplace keys, and the user chooses this knowingly.

The trade-off is surfaced at the moment of choice: Door 1 is safer but needs a
double-click; Door 2 is fully terminal-free but the key is in the transcript.

## Components & changes

### 1. Consent gate for chat tools that ingest a secret
A small shared helper (mirrors the existing `confirm_write` /
`i_understand_this_modifies_data` pattern in `core/safety.py`): any chat tool
that accepts raw `credentials` requires `i_understand_key_goes_to_chat=True`.
Without it, nothing is written and the tool returns an error envelope explaining
the risk and pointing at Door 1 (the installer) as the safe alternative.

Applies to **both** chat tools that take a secret: the new `*_set_key` and the
existing `*_add_cabinet` MCP tool. `install.py` calls `CredentialStore.add_cabinet`
directly (a different layer) and is unaffected — Door 1 stays frictionless.

### 2. `*_set_key` tool (Door 2 headline)
- Args: `credentials: dict`, `cabinet: str = ""` (default: active),
  `i_understand_key_goes_to_chat: bool = False`.
- Target resolution: explicit `cabinet` → else the active cabinet → else the
  auto-derived shop name (§3) → else `"main"`.
- Upserts the credentials onto the target cabinet (rotation = upsert onto the
  existing one). Credential keys are normalised the same way `add_cabinet` already
  does (`clean`).
- Purpose-built for "change my key", separate from "add a new shop", so the agent
  picks the right verb.

### 3. Auto-naming from seller-info
- Per-service "whoami" descriptor: WB → `wb_get_api_seller_info`
  (`GET /api/v1/seller-info`); Ozon → `ozon_post_v1_seller_info`
  (`POST /v1/seller/info`). Held next to the other per-service config.
- Helper `fetch_shop_name(service, creds) -> str | None`: calls the descriptor's
  endpoint through the existing client and extracts a display name by trying a
  list of candidate fields (WB: `name`, `tradeMark`; Ozon: best-effort candidates
  such as `name`, `company_name`, `result.name` — **the exact Ozon field is
  verified live in a follow-up**; until then the fallback path covers it).
  Returns `None` on any error — never raises.
- When a cabinet is created/set without an explicit name, use the API shop name;
  if `None`, fall back to `"main"` (or a numbered name) / let the user override.
- **Soft, not hard validation.** seller-info can 403 if a WB token lacks that
  category — that does **not** mean the key is dead. So a failed lookup never
  blocks saving the key; we just store it and note "couldn't fetch the shop name".

### 4. Cabinet identity / aliases
- A cabinet name is a free string (Cyrillic/spaces allowed) and doubles as its id.
- Default name = real shop name from §3; a manual alias can override it.
- No separate `label` field (YAGNI). `cabinets.json` shape is unchanged — no
  migration.

### 5. Key-health hint (cheap part of C)
- In the client's error handling (`core/client.py` / `core/errors.py`), enrich
  the envelope on **401/403** with: "auth failed — the key may be expired or
  revoked; rotate it with `*_set_key` (chat) or re-run the installer." Proactive
  TTL warnings are a separate thread.

### 6. Multi-shop onboarding
- Already works via `add_cabinet` / `use_cabinet` / `--cabinet`. Add a light
  interactive loop to `install.py`: "Add another shop? (y/n)" so a seller can set
  up 2–3 at once. Reuses §3 auto-naming where possible.

## Data flow (Door 2, change a key)
1. Agent calls `*_set_key(credentials, [cabinet], i_understand_key_goes_to_chat)`.
2. No consent → error envelope (risk + Door 1 hint), nothing stored. Stop.
3. Consent → resolve target cabinet (§2).
4. Best-effort `fetch_shop_name` (§3): 200 → use as name if none given + "shop X
   confirmed"; failure → keep going, note name not fetched.
5. Upsert creds onto the target cabinet; report what was saved (no secret echoed).

## Error handling & edge cases
- seller-info 403 / network error → soft fallback, key still saved.
- No active cabinet and no name given → name from API, else `"main"`.
- Name collision (same shop name twice) → append a numeric suffix.
- Consent flag missing → hard stop with guidance (no partial write).
- Secrets are never echoed back (consistent with `*_check_auth`).

## Testing
- `set_key` without consent → no write, envelope names the risk + Door 1.
- `set_key` with consent → creds upserted onto the resolved cabinet.
- Auto-name: mocked seller-info 200 → cabinet takes the API name; mocked failure
  → fallback name, key still saved.
- 401/403 envelope carries the rotate hint.
- `add_cabinet` MCP tool now also enforces consent (regression for Door 1: the
  installer path via `CredentialStore` is unaffected).

## Touched code
`core/tools.py` (new `set_key`, consent gate on chat secret-tools, auto-name in
add/set), per-service config (whoami descriptor + `fetch_shop_name`),
`core/client.py`/`core/errors.py` (401/403 rotate hint), `install.py` (multi-shop
loop), `core/credentials.py` (no model change), tests.
