"""Safety invariants for the endpoint catalogs.

The product's central promise is that the safety gate blocks accidental writes.
`call_method` gates on the catalog's `safety` field, so a mutating HTTP verb
(PUT/PATCH/DELETE) marked `read` would slip through the gate and execute
immediately. These tests make that promise machine-checkable: they fail if any
catalog entry — or the runtime fallback — lets a mutating verb be treated as a
read.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.registry import Catalog
from core.safety import infer_safety

ROOT = Path(__file__).resolve().parent.parent
CATALOGS = {
    "wb": ROOT / "wb_mcp" / "endpoints.yaml",
    "ozon": ROOT / "ozon_mcp" / "endpoints.yaml",
    "ozon-perf": ROOT / "ozon_mcp" / "perf_endpoints.yaml",
}
MUTATING_VERBS = {"PUT", "PATCH", "DELETE"}


@pytest.mark.parametrize("name,path", list(CATALOGS.items()))
def test_no_mutating_verb_is_marked_read(name, path):
    """PUT/PATCH/DELETE must never carry safety: read — that bypasses the gate."""
    cat = Catalog.from_yaml(path)
    offenders = [
        f"{s.operation_id} ({s.method} {s.path}) -> safety:{s.safety}"
        for s in cat.all()
        if s.method.upper() in MUTATING_VERBS and s.safety == "read"
    ]
    assert not offenders, (
        f"[{name}] {len(offenders)} mutating endpoint(s) marked read — these "
        f"slip past the safety gate in call_method:\n  " + "\n  ".join(offenders)
    )


def test_infer_safety_never_downgrades_mutating_verbs():
    """Even if the catalog says read, a mutating verb must not infer as read."""
    for verb in MUTATING_VERBS:
        assert infer_safety(verb, "read") != "read", (
            f"{verb} declared read still inferred read — runtime gate would skip it"
        )
    # a stricter declaration on a mutating verb is honoured
    assert infer_safety("PUT", "destructive") == "destructive"
    # POST-with-body reads stay reads (legitimate search/list endpoints)
    assert infer_safety("POST", "read") == "read"
    assert infer_safety("GET", "read") == "read"
