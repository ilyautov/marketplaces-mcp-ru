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
