# Self-evident Method & Entity Map Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the 793-method catalog self-evident to the agent/LLM via a curated business-entity taxonomy that powers a new `*_map` tool and synonym/stopword-aware search.

**Architecture:** One shared `core/entities.yaml` (10 entities, each with RU/EN synonyms and lowercase section-name substrings) is loaded by `core/entities.py:EntityIndex`. The index tags every `EndpointSpec` with its entity at catalog load, boosts entity-matched results in `search`, and feeds a per-service `*_map` overview tool. All layers degrade to today's behaviour when the index is absent.

**Tech Stack:** Python 3.10+, PyYAML, FastMCP, pytest (driven via `asyncio.run`, no pytest-asyncio).

---

## File Structure

- **Create** `core/entities.yaml` — curated taxonomy (data, source of truth).
- **Create** `core/entities.py` — `EntityIndex`: load, `entity_of`, `expand`, `stopwords`.
- **Create** `tests/test_entities.py` — taxonomy load, coverage guard, expand, integration.
- **Modify** `core/registry.py` — `EndpointSpec.entity` field; `Catalog(__init__/from_yaml)` accept an index and tag specs; entity-aware `search`.
- **Modify** `core/tools.py` — `register_generic_tools` gains `entities`; new `*_map` tool; entity tag in `search_methods` + `describe_method` output.
- **Modify** `wb_mcp/server.py`, `ozon_mcp/server.py`, `ozon_perf_mcp/server.py` — build one `EntityIndex`, pass to `Catalog.from_yaml` and `register_generic_tools`.
- **Modify** `CHANGELOG.md` — note the feature under `[Unreleased]`.

Run all tests with: `env -u OZON_CLIENT_ID -u OZON_API_KEY -u WB_API_TOKEN python3 -m pytest tests/ -q`

---

## Task 1: Curated taxonomy data (`core/entities.yaml`)

**Files:**
- Create: `core/entities.yaml`
- Test: `tests/test_entities.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_entities.py
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.entities import EntityIndex  # noqa: E402


def test_taxonomy_loads_and_is_well_formed():
    idx = EntityIndex.load()
    assert len(idx.entities) >= 8
    keys = [e["key"] for e in idx.entities]
    assert "reviews" in keys and "stocks" in keys and "prices" in keys
    assert len(keys) == len(set(keys))  # keys unique
    for e in idx.entities:
        assert e["key"] and e["title_ru"] and e["title_en"]
        assert e["synonyms"], f"{e['key']} has no synonyms"
        assert e["match"], f"{e['key']} has no section-match substrings"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_entities.py::test_taxonomy_loads_and_is_well_formed -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.entities'`

- [ ] **Step 3: Create the taxonomy file**

```yaml
# core/entities.yaml
# Curated business-entity taxonomy shared across WB / Ozon / Ozon-perf.
# `match` = lowercase substrings tested against a catalog section name (RU + EN).
# `synonyms` = lowercase words/phrases a user might type; expanded in search.
entities:
  - key: products
    title_ru: Товары и карточки
    title_en: Products & cards
    synonyms: [товар, товары, карточка, карточки, карточек, контент, описание,
               характеристики, категория, категории, медиа, штрихкод, сертификат,
               product, card, content, category, sku, barcode]
    match: [товар, карточк, контент, характеристик, категори, предмет, медиа,
            штрихкод, рекомендац, скрыт, предложен, content, product, categor,
            barcode, quant, digital, certificat, сертификат, offer]
  - key: prices
    title_ru: Цены и скидки
    title_en: Prices & discounts
    synonyms: [цена, цены, цену, ценой, скидка, скидки, акция, акции, наценка,
               уценка, price, prices, discount, promo price, strategy]
    match: [цен, скидк, акци, price, strateg, премиум, premium]
  - key: stocks
    title_ru: Остатки и склады
    title_en: Stocks & warehouses
    synonyms: [остаток, остатки, остатков, склад, склады, хранение, запас,
               запасы, stock, stocks, warehouse, inventory]
    match: [остат, склад, хранен, stock, warehouse]
  - key: orders
    title_ru: Заказы и доставка
    title_en: Orders & delivery
    synonyms: [заказ, заказы, заказов, отгрузка, доставка, сборочное задание,
               отправление, возврат, возвраты, отмена, маркировка, order, orders,
               posting, delivery, shipment, return, returns, cancel, marking]
    match: [заказ, сборочн, order, fbs, fbo, dbs, dbw, самовывоз, доставк,
            delivery, posting, ярлык, пропуск, pass, маркировк, идентификатор,
            marketplace, возврат, return, отмен, cancel, receipt, polygon, полигон]
  - key: supplies
    title_ru: Поставки и приёмка
    title_en: Supplies & inbound
    synonyms: [поставка, поставки, поставок, приёмка, приемка, отгрузка на склад,
               supply, supplies, inbound, draft, dropoff, pickup]
    match: [поставк, приёмк, приемк, supply, draft, dropoff, pickup, fbp]
  - key: reviews
    title_ru: Отзывы и вопросы
    title_en: Reviews & questions
    synonyms: [отзыв, отзывы, отзывов, оценка, оценки, рейтинг, обратная связь,
               вопрос, вопросы, чат, review, reviews, feedback, rating, question,
               chat]
    match: [отзыв, вопрос, оцен, рейтинг, review, question, rating, chat, чат,
            feedback]
  - key: analytics
    title_ru: Аналитика и продажи
    title_en: Analytics & sales
    synonyms: [аналитика, статистика, продажи, выручка, воронка, отчёт, отчет,
               отчёты, поисковые запросы, динамика, analytics, statistics, sales,
               funnel, report, reports, search queries]
    match: [аналитик, статистик, воронк, продаж, поиск, search, analytic,
            statistic, funnel, report, отчёт, отчет, кластер, доля бренда]
  - key: finance
    title_ru: Финансы и выплаты
    title_en: Finance & payouts
    synonyms: [финансы, выплата, выплаты, баланс, удержание, удержания, комиссия,
               комиссии, тариф, тарифы, документ, счёт, finance, payout, balance,
               commission, invoice, document]
    match: [финанс, выплат, удержан, комисс, тариф, finance, invoice, документ,
            document, баланс]
  - key: ads
    title_ru: Реклама и продвижение
    title_en: Ads & promotion
    synonyms: [реклама, продвижение, кампания, кампании, ставки, ставка, бюджет,
               ads, advertising, campaign, promotion, bid]
    match: [реклам, продвижен, кампани, campaign, promotion, promot]
  - key: account
    title_ru: Аккаунт и доступ
    title_en: Account & access
    synonyms: [продавец, кабинет, пользователь, пользователи, доступ, токен,
               ключ, подключение, новости, уведомления, seller, account, user,
               access, token, key, notification]
    match: [продавц, пользовател, систем, подключени, ключ, новост, seller, user,
            system, notification, уведомлен]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_entities.py::test_taxonomy_loads_and_is_well_formed -v`
Expected: PASS (after Task 2 creates `core/entities.py`). If `core/entities.py` does not exist yet, this fails on import — proceed to Task 2, then re-run. To keep TDD strict, write Task 2's `EntityIndex.load` minimal body before re-running this test.

- [ ] **Step 5: Commit**

```bash
git add core/entities.yaml tests/test_entities.py
git commit -m "feat(#8): curated entity taxonomy data"
```

---

## Task 2: `EntityIndex` loader + `entity_of` (`core/entities.py`)

**Files:**
- Create: `core/entities.py`
- Test: `tests/test_entities.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_entities.py
from types import SimpleNamespace  # noqa: E402


def _spec(section):
    return SimpleNamespace(section=section, operation_id="x", summary="", path="")


def test_entity_of_matches_by_section_substring():
    idx = EntityIndex.load()
    assert "reviews" in idx.entity_of(_spec("Отзывы"))
    assert "reviews" in idx.entity_of(_spec("Questions&Answers"))
    assert "stocks" in idx.entity_of(_spec("История остатков"))
    assert "orders" in idx.entity_of(_spec("fbs"))
    assert "prices" in idx.entity_of(_spec("Цены и скидки"))
    assert idx.entity_of(_spec("totally-unknown-section")) == []


def test_missing_yaml_degrades_gracefully():
    idx = EntityIndex.load(path="/nonexistent/entities.yaml")
    assert idx.entities == []
    assert idx.entity_of(_spec("Отзывы")) == []
    assert idx.expand("дай отзывы")[1] == set()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_entities.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.entities'`

- [ ] **Step 3: Write the implementation**

```python
# core/entities.py
"""Business-entity taxonomy: makes the catalog legible to the agent/LLM.

Loads a curated `entities.yaml` and exposes three things the tools use:
- entity_of(spec)  -> which business entities a method belongs to
- expand(query)    -> (cleaned tokens, matched entity keys) for smarter search
- stopwords        -> RU/EN noise words stripped from queries

Every method degrades gracefully: a missing/broken yaml yields an empty index,
and callers fall back to the pre-entity behaviour.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

_DEFAULT_PATH = Path(__file__).resolve().parent / "entities.yaml"

# RU/EN filler words that carry no routing signal.
STOPWORDS: set[str] = {
    "дай", "дайка", "покажи", "показать", "мне", "мой", "моя", "мои", "что",
    "какие", "какой", "сколько", "по", "на", "с", "со", "в", "во", "и", "а",
    "у", "за", "до", "от", "как", "есть", "это", "пожалуйста", "ну",
    "please", "show", "get", "list", "all", "me", "my", "the", "a", "of", "for",
}


class EntityIndex:
    def __init__(self, entities: list[dict[str, Any]]):
        self.entities = entities
        self.stopwords = STOPWORDS
        # synonym phrase -> entity key (lowercased)
        self._syn: dict[str, str] = {}
        for e in entities:
            self._syn[e["key"].lower()] = e["key"]
            for syn in e.get("synonyms", []):
                self._syn[syn.lower()] = e["key"]

    @classmethod
    def load(cls, path: str | Path | None = None) -> "EntityIndex":
        p = Path(path) if path else _DEFAULT_PATH
        try:
            raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            entities = raw.get("entities", [])
            assert isinstance(entities, list)
        except Exception:  # noqa: BLE001 — never break the server on a bad file
            entities = []
        return cls(entities)

    def entity_of(self, spec: Any) -> list[str]:
        """Entity keys for a spec via lowercase section-name substring match."""
        section = (getattr(spec, "section", "") or "").lower()
        if not section:
            return []
        keys: list[str] = []
        for e in self.entities:
            if any(sub in section for sub in e.get("match", [])):
                keys.append(e["key"])
        return keys

    def expand(self, query: str) -> tuple[list[str], set[str]]:
        """Return (cleaned tokens, matched entity keys).

        - cleaned tokens: lowercased, stopwords removed (still feed token search).
        - entity keys: any synonym phrase contained in the query maps to its entity.
        """
        q = query.lower()
        tokens = [t for t in re.split(r"[^\w]+", q) if t and t not in self.stopwords]
        keys: set[str] = set()
        for syn, key in self._syn.items():
            if " " in syn:
                if syn in q:
                    keys.add(key)
            elif syn in tokens:
                keys.add(key)
        return tokens, keys
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_entities.py -v`
Expected: PASS (3 tests: taxonomy load, entity_of, graceful degrade)

- [ ] **Step 5: Commit**

```bash
git add core/entities.py tests/test_entities.py
git commit -m "feat(#8): EntityIndex loader, entity_of, expand"
```

---

## Task 3: Coverage guard + expand behaviour

**Files:**
- Test: `tests/test_entities.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_entities.py
from core.registry import Catalog  # noqa: E402

CATALOGS = {
    "wb": "wb_mcp/endpoints.yaml",
    "ozon": "ozon_mcp/endpoints.yaml",
    "ozon_perf": "ozon_mcp/perf_endpoints.yaml",
}


def test_expand_strips_stopwords_and_maps_synonyms():
    idx = EntityIndex.load()
    tokens, keys = idx.expand("дай мне отзывы")
    assert "дай" not in tokens and "мне" not in tokens
    assert "reviews" in keys
    assert "stocks" in idx.expand("что с остатками")[1] or \
           "stocks" in idx.expand("остатки")[1]
    assert "reviews" in idx.expand("оценки покупателей")[1]


def test_taxonomy_covers_at_least_85pct_of_each_catalog():
    idx = EntityIndex.load()
    for svc, path in CATALOGS.items():
        specs = Catalog.from_yaml(path).all()
        mapped = sum(1 for s in specs if idx.entity_of(s))
        ratio = mapped / len(specs)
        assert ratio >= 0.85, f"{svc}: only {ratio:.0%} of methods mapped to an entity"
```

- [ ] **Step 2: Run test to verify it fails or reveals gaps**

Run: `python3 -m pytest tests/test_entities.py::test_taxonomy_covers_at_least_85pct_of_each_catalog -v`
Expected: PASS if the taxonomy is broad enough; if it FAILS with e.g. "only 78% mapped", print the unmapped sections and widen `match` lists in `core/entities.yaml` until ≥85%. Diagnostic one-liner:

```bash
python3 -c "
from core.entities import EntityIndex; from core.registry import Catalog
import collections
idx=EntityIndex.load()
for svc,p in {'wb':'wb_mcp/endpoints.yaml','ozon':'ozon_mcp/endpoints.yaml','ozon_perf':'ozon_mcp/perf_endpoints.yaml'}.items():
    un=collections.Counter(s.section for s in Catalog.from_yaml(p).all() if not idx.entity_of(s))
    print(svc, 'unmapped sections:', un.most_common())
"
```

- [ ] **Step 3: Widen `match` lists if needed**

Edit `core/entities.yaml` only — add the missing section substrings printed above to the closest entity's `match` list. Do not add new entities. Re-run until the guard passes.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_entities.py -v`
Expected: PASS (all 5 tests)

- [ ] **Step 5: Commit**

```bash
git add tests/test_entities.py core/entities.yaml
git commit -m "test(#8): coverage guard (>=85%) + expand behaviour"
```

---

## Task 4: Tag specs at catalog load (`core/registry.py`)

**Files:**
- Modify: `core/registry.py:31-50` (EndpointSpec), `:65-73` (to_summary_dict), `:79-94` (Catalog)
- Test: `tests/test_registry_entity.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_registry_entity.py
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.entities import EntityIndex  # noqa: E402
from core.registry import Catalog  # noqa: E402


def test_specs_get_entity_tags_when_index_supplied():
    idx = EntityIndex.load()
    cat = Catalog.from_yaml("wb_mcp/endpoints.yaml", entities=idx)
    review_specs = [s for s in cat.all() if "reviews" in s.entity]
    assert review_specs, "expected some methods tagged 'reviews'"
    assert "entity" in review_specs[0].to_summary_dict()


def test_no_index_means_empty_entity_tags():
    cat = Catalog.from_yaml("wb_mcp/endpoints.yaml")
    assert all(s.entity == [] for s in cat.all())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_registry_entity.py -v`
Expected: FAIL with `TypeError: from_yaml() got an unexpected keyword argument 'entities'`

- [ ] **Step 3: Modify `core/registry.py`**

Add the field to `EndpointSpec` (after `params`, around line 50):

```python
    # free-form param hints surfaced in describe_method
    params: dict[str, Any] = field(default_factory=dict)
    # business-entity tags, filled at catalog load from EntityIndex (see entities.py)
    entity: list[str] = field(default_factory=list)
```

Add `entity` to `to_summary_dict` (around line 65):

```python
    def to_summary_dict(self) -> dict:
        return {
            "operation_id": self.operation_id,
            "section": self.section,
            "method": self.method,
            "path": self.path,
            "safety": self.safety,
            "summary": self.summary,
            "entity": self.entity,
        }
```

Replace `Catalog.__init__` and `from_yaml` (lines 79-94):

```python
    def __init__(self, specs: list[EndpointSpec], default_host: str = "",
                 entities: "Any" = None):
        self.default_host = default_host
        self.entities = entities  # EntityIndex | None — used by search()
        self._by_id: dict[str, EndpointSpec] = {}
        for s in specs:
            if not s.host:
                s.host = default_host
            if entities is not None:
                s.entity = entities.entity_of(s)
            self._by_id[s.operation_id] = s

    @classmethod
    def from_yaml(cls, path: str | Path, default_host: str = "",
                  entities: "Any" = None) -> "Catalog":
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        default_host = raw.get("default_host", default_host)
        specs: list[EndpointSpec] = []
        for rec in raw.get("endpoints", []):
            specs.append(EndpointSpec(**rec))
        return cls(specs, default_host=default_host, entities=entities)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_registry_entity.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add core/registry.py tests/test_registry_entity.py
git commit -m "feat(#8): tag EndpointSpec with entity at catalog load"
```

---

## Task 5: Entity-aware search (`core/registry.py:search`)

**Files:**
- Modify: `core/registry.py:111-138` (`search`)
- Test: `tests/test_registry_entity.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_registry_entity.py
def test_search_boosts_entity_match_over_stopword_noise():
    idx = EntityIndex.load()
    cat = Catalog.from_yaml("wb_mcp/endpoints.yaml", entities=idx)
    results = cat.search("дай отзывы", limit=5)
    assert results, "search returned nothing"
    # the top hit should be a reviews method, not noise from the verb "дай"
    assert "reviews" in results[0].entity


def test_search_without_index_still_works():
    cat = Catalog.from_yaml("wb_mcp/endpoints.yaml")
    assert cat.search("stocks", limit=3)  # pure token overlap, unchanged
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_registry_entity.py::test_search_boosts_entity_match_over_stopword_noise -v`
Expected: FAIL — `assert "reviews" in results[0].entity` (today "дай" pollutes scoring and reviews may not rank first)

- [ ] **Step 3: Replace `search` in `core/registry.py`**

```python
    def search(self, query: str, limit: int = 15) -> list[EndpointSpec]:
        """Token-overlap scoring with optional entity awareness.

        When an EntityIndex is attached, stopwords are stripped from the query
        and a spec whose entity matches the query's entity gets a strong boost.
        Falls back to plain token overlap when no index is present.
        """
        if self.entities is not None:
            terms, entity_keys = self.entities.expand(query)
        else:
            terms = [t for t in re.split(r"[^\w]+", query.lower()) if t]
            entity_keys = set()
        if not terms and not entity_keys:
            return []
        scored: list[tuple[float, EndpointSpec]] = []
        for s in self._by_id.values():
            hay = " ".join(
                [s.operation_id, s.summary, s.path, s.section, s.scope]
                + s.keywords
            ).lower()
            score = 0.0
            for t in terms:
                if t in hay:
                    score += 1.0
                if t in s.operation_id.lower():
                    score += 0.5
                if t == s.section.lower():
                    score += 0.5
            if entity_keys and set(s.entity) & entity_keys:
                score += 2.0  # entity match dominates incidental token hits
            if score > 0:
                scored.append((score, s))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [s for _, s in scored[:limit]]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_registry_entity.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add core/registry.py tests/test_registry_entity.py
git commit -m "feat(#8): entity-aware search with stopword stripping + boost"
```

---

## Task 6: `*_map` tool + entity in tool output (`core/tools.py`)

**Files:**
- Modify: `core/tools.py:36-49` (`register_generic_tools` signature), add `map` tool near `search_methods` (`:100-119`)
- Test: `tests/test_entity_map_tool.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_entity_map_tool.py
from __future__ import annotations
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _tools(server):
    return {t.name for t in asyncio.run(server.mcp.list_tools())}


def _call(server, name, args):
    # FastMCP call_tool returns a tuple: ([TextContent(text=...)], <meta>)
    res = asyncio.run(server.mcp.call_tool(name, args))
    return json.loads(res[0][0].text)


def test_map_tool_registered_on_all_servers():
    import wb_mcp.server as wb
    import ozon_mcp.server as oz
    import ozon_perf_mcp.server as pf
    assert "wb_map" in _tools(wb)
    assert "ozon_map" in _tools(oz)
    assert "ozon_perf_map" in _tools(pf)


def test_map_overview_lists_entities_with_counts():
    import wb_mcp.server as wb
    payload = _call(wb, "wb_map", {})
    keys = {e["key"] for e in payload["entities"]}
    assert "reviews" in keys
    rev = next(e for e in payload["entities"] if e["key"] == "reviews")
    assert rev["method_count"] >= 1
    assert rev["title_ru"] and isinstance(rev["headline"], list)


def test_map_zoom_lists_methods_of_one_entity():
    import wb_mcp.server as wb
    payload = _call(wb, "wb_map", {"entity": "reviews"})
    assert payload["entity"] == "reviews"
    assert payload["methods"], "zoom should list reviews methods"
    assert all("reviews" in m.get("entity", []) for m in payload["methods"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_entity_map_tool.py::test_map_tool_registered_on_all_servers -v`
Expected: FAIL — `assert "wb_map" in _tools(wb)` (tool not registered yet)

- [ ] **Step 3: Modify `core/tools.py`**

Change the `register_generic_tools` signature (line ~36) to accept the index:

```python
def register_generic_tools(
    mcp: FastMCP,
    *,
    svc: str,
    client: MarketplaceClient,
    catalog: Catalog,
    key_help: str = "",
    entities: Optional[Any] = None,
) -> None:
```

Immediately after the `search_methods` tool definition (after its `return _j(...)`,
around line 119), add the map tool:

```python
    @mcp.tool(
        name=f"{svc}_map",
        annotations={"title": f"{svc.upper()} capabilities map",
                     "readOnlyHint": True, "openWorldHint": False},
    )
    async def entity_map(entity: str = "") -> str:
        """The big picture: business entities this API covers and the go-to
        methods for each. Call with no args to see the whole map ("you are
        here"); pass entity="reviews" (or stocks/prices/orders/…) to list every
        method of one entity. Use this before guessing — it orients you fast.
        """
        ents = entities.entities if entities is not None else []
        by_key: dict[str, list] = {}
        for s in catalog.all():
            for k in (s.entity or ["other"]):
                by_key.setdefault(k, []).append(s)
        if entity:
            specs = by_key.get(entity, [])
            return _j({"entity": entity, "count": len(specs),
                       "methods": [s.to_summary_dict() for s in specs]})
        out = []
        for e in ents:
            specs = by_key.get(e["key"], [])
            if not specs:
                continue
            headline = [s for s in specs if s.operation_id in e.get("headline", [])]
            shown = headline or specs[:5]
            out.append({
                "key": e["key"], "title_ru": e["title_ru"],
                "title_en": e["title_en"], "synonyms": e["synonyms"],
                "method_count": len(specs),
                "headline": [s.to_summary_dict() for s in shown],
            })
        if by_key.get("other"):
            out.append({"key": "other", "title_ru": "Прочее", "title_en": "Other",
                        "synonyms": [], "method_count": len(by_key["other"]),
                        "headline": []})
        return _j({"service": svc, "entities": out})
```

Confirm `Any` is imported (line 22 already has `from typing import Any, Optional`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_entity_map_tool.py -v`
Expected: FAIL on the call_tool tests until Task 8 wires `entities=` into the
servers (registration test also needs the wiring). Run the registration test
after Task 8. For now verify the file imports cleanly:
`python3 -c "import core.tools"` → no error.

- [ ] **Step 5: Commit**

```bash
git add core/tools.py tests/test_entity_map_tool.py
git commit -m "feat(#8): *_map tool (overview + entity zoom)"
```

---

## Task 7: Entity tag in describe_method output

**Files:**
- Modify: `core/tools.py` `describe_method` (around line 121-140)
- Test: covered by `tests/test_entity_map_tool.py` (add one case)

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_entity_map_tool.py
def test_describe_method_includes_entity_tag():
    import wb_mcp.server as wb
    review = next(s for s in wb.catalog.all() if "reviews" in s.entity)
    payload = _call(wb, "wb_describe_method", {"operation_id": review.operation_id})
    assert "reviews" in payload.get("entity", [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_entity_map_tool.py::test_describe_method_includes_entity_tag -v`
Expected: FAIL (entity key absent from describe output) — run after Task 8 wiring.

- [ ] **Step 3: Modify `describe_method`**

`describe_method` builds its own dict (it does NOT use `to_summary_dict`). In its
returned `_j({...})`, add `"entity": spec.entity,` right after `"section": spec.section,`:

```python
        return _j({
            "operation_id": spec.operation_id, "section": spec.section,
            "entity": spec.entity,
            "method": spec.method, "host": spec.host, "path": spec.path,
            "path_params": spec.path_params, "scope": spec.scope,
            "safety": spec.safety, "pagination": spec.pagination,
            "rate_limit": spec.rate_limit, "summary": spec.summary,
            "params": spec.params, "doc": spec.doc,
        })
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_entity_map_tool.py::test_describe_method_includes_entity_tag -v`
Expected: PASS (after Task 8 wiring)

- [ ] **Step 5: Commit**

```bash
git add core/tools.py tests/test_entity_map_tool.py
git commit -m "feat(#8): expose entity tag in describe_method"
```

---

## Task 8: Wire the index into the three servers

**Files:**
- Modify: `wb_mcp/server.py:45-54`, `ozon_mcp/server.py:47-54`, `ozon_perf_mcp/server.py:66-73`

- [ ] **Step 1: (tests already written in Tasks 6-7)**

Run the full map-tool suite now to confirm it currently fails on wiring:
Run: `python3 -m pytest tests/test_entity_map_tool.py -v`
Expected: FAIL (tools not yet wired with the index)

- [ ] **Step 2: Modify `wb_mcp/server.py`**

At the top, add the import (next to the other `core` imports):

```python
from core.entities import EntityIndex
```

Replace the catalog construction + `register_generic_tools` call (lines ~46-54):

```python
mcp = FastMCP("wb_mcp")
entities = EntityIndex.load()
catalog = Catalog.from_yaml(CATALOG_PATH, entities=entities)
client = MarketplaceClient(WB_CONFIG)

register_generic_tools(
    mcp, svc="wb", client=client, catalog=catalog, entities=entities,
    key_help="seller.wildberries.ru → Settings → Access tokens (one token, "
             "select the categories you need).",
)
```

- [ ] **Step 3: Modify `ozon_mcp/server.py` and `ozon_perf_mcp/server.py`**

`ozon_mcp/server.py` — add `from core.entities import EntityIndex`, then:

```python
mcp = FastMCP("ozon_mcp")
entities = EntityIndex.load()
catalog = Catalog.from_yaml(CATALOG_PATH, entities=entities)
client = MarketplaceClient(OZON_CONFIG)

register_generic_tools(
    mcp, svc="ozon", client=client, catalog=catalog, entities=entities,
    key_help="seller.ozon.ru → Settings → API keys (Client-Id + Api-Key).",
)
```

`ozon_perf_mcp/server.py` — add `from core.entities import EntityIndex`, change
the catalog line (≈67) to `catalog = Catalog.from_yaml(CATALOG_PATH, entities=entities)`
with `entities = EntityIndex.load()` just above it, and add `entities=entities,`
to its `register_generic_tools(...)` call.

- [ ] **Step 4: Run tests + selfcheck**

Run: `python3 -m pytest tests/test_entity_map_tool.py tests/test_registry_entity.py -v`
Expected: PASS (all map + describe + search integration tests)

Run: `for s in wb ozon ozon-perf; do python3 serve.py $s --selfcheck; done`
Expected: each prints `OK: <svc> ready, N tools.` with N one higher than before
(the new `*_map` tool): wb 21, ozon 21, ozon-perf 16.

- [ ] **Step 5: Commit**

```bash
git add wb_mcp/server.py ozon_mcp/server.py ozon_perf_mcp/server.py
git commit -m "feat(#8): wire EntityIndex into all three servers"
```

---

## Task 9: Full suite, CHANGELOG, final commit

**Files:**
- Modify: `CHANGELOG.md:6` (under `[Unreleased]`)

- [ ] **Step 1: Run the entire test suite**

Run: `env -u OZON_CLIENT_ID -u OZON_API_KEY -u WB_API_TOKEN python3 -m pytest tests/ -q`
Expected: PASS — 39 prior tests + the new entity tests, all green.

- [ ] **Step 2: Add a CHANGELOG entry**

Insert after the `## [Unreleased]` heading (line 6), above the `### Добавлено — кабинеты` block:

```markdown
### Добавлено — самоочевидная карта методов и сущностей (#8)
- **Тул `*_map`** — обзор возможностей сервиса: бизнес-сущности (Товары, Цены,
  Остатки, Заказы, Поставки, Отзывы, Аналитика, Финансы, Реклама, Аккаунт) с
  синонимами, счётчиками и ключевыми методами. `entity="reviews"` — зум в одну
  сущность. Один вызов = вся карта, агент не теряется в 793 методах.
- **Умный поиск.** `*_search_methods` срезает стоп-слова («дай/покажи/мне»),
  понимает синонимы («оценки»→отзывы, «остатки»→stocks) и поднимает методы
  нужной сущности наверх. Сырые EN-токены работают как раньше.
- **Тег сущности** в выводе `search_methods` и `describe_method`.
- Курируемая таксономия — `core/entities.yaml` (10 сущностей, RU/EN-синонимы,
  пер-сервисный матч по секциям). Дизайн —
  `docs/superpowers/specs/2026-06-24-method-entity-map-design.md`.
```

- [ ] **Step 3: Run selfcheck once more**

Run: `for s in wb ozon ozon-perf; do python3 serve.py $s --selfcheck; done`
Expected: `OK` for all three.

- [ ] **Step 4: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs(#8): changelog for method & entity map"
```

- [ ] **Step 5: Push**

```bash
git push origin main
```

---

## Self-Review notes (for the implementer)

- The `*_map` `call_tool` return shape varies by FastMCP version. Before relying on
  `json.loads(call_tool(...))`, confirm whether it returns a string or a content
  list (the Task 6 NOTE has the probe). `tests/test_mock.py` already calls
  `mcp.list_tools()` successfully — mirror its style for `call_tool`.
- Coverage guard is set at 85%. If real coverage is far higher, leave the
  threshold at 85% (headroom for catalog growth); do not tighten to a brittle 100%.
- Do not add workflow routing here — it is explicitly a future skill-pack.
