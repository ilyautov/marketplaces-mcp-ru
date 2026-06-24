# tests/test_entities.py
from __future__ import annotations
import sys
from pathlib import Path
from types import SimpleNamespace

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
