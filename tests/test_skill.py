# -*- coding: utf-8 -*-
"""Скилл это отдельная поверхность установки, и ломается она тихо.

Спека Agent Skills режет `description` на 1024 символах, а лишнее поле во
фронтматтере отказывает установке целиком, без предупреждения. Числа в теле
скилла должны совпадать с каталогом, который реально едет с пакетом: разойтись
им проще всего, потому что скилл читает человек, а каталог исполняет сервер.
"""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "marketplaces-mcp" / "SKILL.md"

CATALOGS = {
    "ozon_mcp/endpoints.yaml": 441,
    "wb_mcp/endpoints.yaml": 307,
    "yandex_mcp/endpoints.yaml": 165,
    "avito_mcp/endpoints.yaml": 64,
    "ozon_mcp/perf_endpoints.yaml": 45,
}


def _front() -> str:
    return SKILL.read_text(encoding="utf-8").split("---")[1]


def test_frontmatter_has_exactly_the_two_allowed_fields():
    fields = [ln.split(":", 1)[0] for ln in _front().splitlines()
              if ln and not ln.startswith(" ")]
    assert set(fields) == {"name", "description"}, fields


def test_description_fits_the_spec_limit():
    desc = _front().split('description: "', 1)[1].rsplit('"', 1)[0]
    assert len(desc) <= 1024, len(desc)


def test_numbers_match_the_catalogs_that_ship():
    text = SKILL.read_text(encoding="utf-8")
    total = 0
    for rel, expected in CATALOGS.items():
        rows = yaml.safe_load((ROOT / rel).read_text(encoding="utf-8"))["endpoints"]
        assert len(rows) == expected, f"{rel}: каталог изменился, поправь скилл"
        assert f"| {expected} |" in text, f"{rel}: числа нет в таблице скилла"
        total += expected
    assert str(total) in text, f"общее число методов должно быть {total}"


def test_no_skill_in_repository_root():
    """Корневой SKILL.md заставляет `npx skills add` считать скиллом весь
    репозиторий и копировать его пользователю целиком."""
    assert not (ROOT / "SKILL.md").exists()
