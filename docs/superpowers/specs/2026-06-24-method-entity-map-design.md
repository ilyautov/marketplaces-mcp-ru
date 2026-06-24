# Self-evident method & entity map — design

Date: 2026-06-24
Status: approved for implementation
Scope: subproject #8 of the "terminal-free everywhere" north star.

## Goal

Make the 793-method catalog **self-evident to the agent/LLM**: it should see the
business-entity map at a glance and resolve loose Russian phrases ("что с
отзывами", "дай остатки", "подними цену") to the right methods without getting
lost. The agent never has to guess blindly across 793 endpoints.

### Out of scope (separate threads)
- **Workflow / recipe routing** — multi-step "what should I reorder" guidance
  moves to a separate **skill-pack on top of the MCP** (the user's call). This
  spec does not touch `workflows.yaml` or add intent→workflow routing.
- Full morphology / stemming engine. We use a curated synonym dictionary +
  stopwords, not an NLP library (YAGNI; light stemming can be added later).
- Encryption, key lifecycle, install — covered elsewhere.

## North star

One curated taxonomy of business entities, shared across services, feeds two
surfaces the agent already reaches for: a new **map tool** ("you are here") and
the existing **search**. Both read the same source of truth, so the vocabulary
the LLM uses ("оценки", "обратная связь") and the map it sees never drift apart.

## Components & changes

### 1. `core/entities.yaml` — the curated taxonomy (source of truth)
A compact list (~12–16) of business entities a marketplace seller reasons about:
Товары/карточки, Цены и скидки, Остатки и склады, Заказы (FBS/FBO), Поставки,
Отзывы и вопросы, Аналитика/продажи, Финансы/выплаты, Реклама/продвижение, …

Per entity:
- `key` — stable id (`reviews`, `stocks`, `prices`, …). Shared across services.
- `title_ru`, `title_en` — display names.
- `synonyms` — RU/EN words and short phrases that should resolve here
  (`отзывы, оценки, обратная связь, отзыв, feedback, reviews`). Lowercased.
- `sections` — **service-aware** map of which catalog `section` values belong to
  this entity: `{wb: [...], ozon: [...], ozon_perf: [...]}`. Drives auto-tagging.
- `headline` (optional) — a few `operation_id`s to surface as the go-to methods.
  Empty → the map tool falls back to the first N methods of the entity's sections.

### 2. `core/entities.py` — `EntityIndex`
Loads `entities.yaml` once and exposes:
- `entity_of(spec) -> list[str]` — entity keys for a spec, via `section` match
  (service-aware) plus any per-`operation_id` curated override. No match → `[]`
  (the caller buckets it as `other`).
- `expand(query) -> ExpansionResult` — lowercase, split, drop stopwords, map
  surviving tokens/phrases through the synonym index to (entity keys, canonical
  terms). Returns the cleaned tokens + matched entity keys.
- `stopwords` — RU/EN noise set (`дай, покажи, мне, дай-ка, please, show, get, …`).
- `taxonomy(service) -> list[entity dicts]` — for the map tool, scoped to a service.
- Graceful degradation: missing/malformed yaml → empty index; every method below
  returns the pre-#8 behaviour (no tags, plain token search).

### 3. `*_map` tool (new, per service)
- No-arg: returns the service's taxonomy — for each entity present in this
  service's catalog: `key`, `title_ru/en`, `synonyms`, `method_count`, and 3–5
  `headline` methods (`operation_id` + `summary`). Plus an `other` bucket if any
  methods are unmapped. This is the agent's single-call "you are here".
- `entity="reviews"`: zoom — list **all** methods of that entity (id + summary +
  method + safety), so the agent drills down without 5 searches.
- Read-only annotation.

### 4. `search_methods` upgrade (in `core/registry.py`)
`search(query)` becomes synonym/entity-aware while staying backward compatible:
1. `EntityIndex.expand(query)` → strip stopwords, map synonyms → entity keys +
   canonical terms; the surviving raw tokens still feed the existing overlap.
2. Existing token-overlap scoring over id/summary/path/section/keywords, **plus a
   boost** when a spec's `entity` is in the query's matched entity keys.
3. No `EntityIndex` (or no match) → identical to today's pure token overlap.

### 5. Entity tag on results
- `EndpointSpec` carries an `entity` field (list), computed at catalog load:
  `Catalog.from_yaml(path, entities=index)` tags each spec via `entity_of`.
  `entities=None` → no tags (graceful, unchanged behaviour).
- `describe_method` **and** `search_methods` output include the `entity` tag(s),
  so the agent learns the method→entity mapping as it explores.

## Data flow (agent asks "что с отзывами")
1. `*_search_methods("что с отзывами")` (or `*_map` first for orientation).
2. `expand`: drop "что/с" stopwords → "отзывами" → synonym index → entity
   `reviews` + canonical "отзывы/feedback".
3. Scoring boosts specs tagged `reviews` → feedbacks/questions methods rank top,
   each carrying `entity: ["reviews"]`.
4. `describe_method` confirms `entity: ["reviews"]`.

## Error handling & edge cases
- `entities.yaml` missing/malformed → empty `EntityIndex`; map tool returns a
  sections-only fallback, search falls back to today's overlap. Never crashes.
- Method matching no entity → bucketed `other`, still listed by the map tool, so
  the map is exhaustive — every one of the 793 methods stays reachable.
- A synonym mapping to two entities → expand to both; both get the boost.
- Section→entity drift as catalogs grow → caught by the coverage guard test.

## Testing (offline, no keys)
- `entities.yaml` loads; each entity has `key`, `title_ru/en`, non-empty `synonyms`.
- **Coverage guard:** every `section` in WB / Ozon / Ozon-perf catalogs maps to an
  entity or `other` — no silent orphan sections.
- `expand`: "оценки"→`reviews`, "остатки"→`stocks`, "дай покажи мне" → all dropped.
- `search_methods("дай отзывы")` ranks a `reviews` method above an unrelated one
  (regression vs the pre-#8 behaviour, where verbs were noise).
- `*_map` registered on all three servers; no-arg returns entities with counts +
  headline; `entity=` zoom lists that entity's methods; unmapped → `other` shown.
- `describe_method` and `search_methods` outputs carry the `entity` tag.
- Graceful: a `Catalog` built with `entities=None` behaves exactly as today.

## Touched code
- **New:** `core/entities.yaml`, `core/entities.py`, `tests/test_entities.py`.
- **Modified:** `core/registry.py` (`EndpointSpec.entity`; synonym/stopword +
  entity-boost in `search`; `from_yaml(entities=…)`), `core/tools.py` (new
  `*_map` tool; entity tag in `search_methods` + `describe_method`), the three
  server files (build one shared `EntityIndex`, pass it to `Catalog.from_yaml`
  and `register_*_tools`).
- **Unchanged:** `workflows.yaml`, credentials, install, safety gate.
