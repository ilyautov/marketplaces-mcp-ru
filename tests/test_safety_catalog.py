"""Safety invariants for the endpoint catalogs.

The product's central promise is that the safety gate blocks accidental writes.
`call_method` gates on the catalog's `safety` field, so a mutating HTTP verb
(PUT/PATCH/DELETE) marked `read` would slip through the gate and execute
immediately. These tests make that promise machine-checkable: they fail if any
catalog entry — or the runtime fallback — lets a mutating verb be treated as a
read.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

from core.registry import Catalog
from core.safety import infer_safety

ROOT = Path(__file__).resolve().parent.parent
CATALOGS = {
    "wb": ROOT / "wb_mcp" / "endpoints.yaml",
    "ozon": ROOT / "ozon_mcp" / "endpoints.yaml",
    "ozon-perf": ROOT / "ozon_mcp" / "perf_endpoints.yaml",
    "yandex": ROOT / "yandex_mcp" / "endpoints.yaml",
    "avito": ROOT / "avito_mcp" / "endpoints.yaml",
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


# A read action in the last path segment. Ozon is ~all POST, so the tail is the
# only reliable signal of intent: /v1/report/list reads, /v1/report/create writes.
# `status` is deliberately absent — it genuinely goes both ways here
# (/v1/order/cancel/status is a write, /v1/warehouse/operation/status a read).
READ_TAIL = re.compile(r"/(list|get|info|search|tree|report)$", re.I)


@pytest.mark.parametrize("name,path", list(CATALOGS.items()))
def test_post_read_tail_is_not_marked_write(name, path):
    """A POST whose path ends in a read action must be catalogued as read.

    Marking one `write` does not leak anything, but it makes the safety gate ask
    for confirmation before a method that only reads. That trains the user to
    click through confirmations, which is exactly how a real write slips by.

    This regressed once already: the Ozon ingest matched its MUTATE pattern
    against the whole path, so the noun in /conditional-cancellation/list
    ("cancel") and /certificate/rejection_reasons/list ("reject") pushed 75 pure
    reads into `write`.
    """
    cat = Catalog.from_yaml(path)
    offenders = [
        f"{s.operation_id} ({s.method} {s.path}) -> safety:{s.safety}"
        for s in cat.all()
        if s.method.upper() == "POST"
        and s.safety != "read"
        and READ_TAIL.search(s.path)
    ]
    assert not offenders, (
        f"[{name}] {len(offenders)} read-only endpoint(s) marked as mutating — "
        f"the gate will ask for confirmation before a plain read:\n  "
        + "\n  ".join(offenders)
    )


def test_ozon_ingest_tail_beats_nouns_in_the_middle():
    """The heuristic itself, so a re-ingest cannot reintroduce the 75."""
    sys.path.insert(0, str(ROOT))
    from scripts.ingest_ozon import safety

    # nouns that used to trigger MUTATE and win over the read tail
    assert safety("POST", "/v1/conditional-cancellation/list", "") == "read"
    assert safety("POST", "/v1/product/certificate/rejection_reasons/list", "") == "read"
    assert safety("POST", "/v1/fbp/draft/list", "") == "read"
    assert safety("POST", "/v1/fbp/archive/get", "") == "read"
    assert safety("POST", "/v2/draft/create/info", "") == "read"

    # and the tail must not rescue anything that really mutates
    assert safety("POST", "/v1/order/cancel/status", "") == "write"
    assert safety("POST", "/v1/product/import", "") == "write"
    assert safety("POST", "/v1/draft/supply/create", "") == "write"
    assert safety("DELETE", "/v1/product/list", "") == "destructive"
    assert safety("PUT", "/v1/something/get", "") == "write"
