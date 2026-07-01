"""Schema-driven endpoint catalog.

The catalog is the source of truth for what the server can do. Each service
ships a YAML file (`endpoints.yaml`) describing endpoints as records. The
generic executor can call ANY endpoint in the catalog by `operation_id`, and
can also call arbitrary paths not in the catalog (full coverage from day one).

A catalog record:
    operation_id: wb_get_sales          # unique, snake_case, service-prefixed
    section: statistics                  # grouping for browse/search
    method: GET
    host: statistics-api.wildberries.ru  # per-endpoint (WB is multi-host)
    path: /api/v1/supplier/sales         # may contain {placeholders}
    scope: statistics                    # token category / permission needed
    safety: read                         # read | write | destructive
    summary: Sales and returns since a date.
    pagination: lastchangedate           # cursor style or 'none'
    rate_limit: "1 req/min"
    doc: https://dev.wildberries.ru/en/openapi/reports
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

import yaml


@dataclass
class EndpointSpec:
    operation_id: str
    method: str
    host: str
    path: str
    section: str = "general"
    scope: str = ""
    safety: str = "read"
    summary: str = ""
    pagination: str = "none"
    # dotted path to the array of rows in a response (varies per endpoint):
    # "result.items", "items", "result.rows", "result.operations", ...
    items_path: str = "result.items"
    rate_limit: str = ""
    doc: str = ""
    # Russian (and other) search aliases so RU queries hit English summaries.
    keywords: list[str] = field(default_factory=list)
    # free-form param hints surfaced in describe_method
    params: dict[str, Any] = field(default_factory=dict)
    # business-entity tags, filled at catalog load from EntityIndex (see entities.py)
    entity: list[str] = field(default_factory=list)

    @property
    def path_params(self) -> list[str]:
        return re.findall(r"\{([^}]+)\}", self.path)

    def render_path(self, values: dict[str, Any]) -> str:
        """Substitute {placeholders}; raises KeyError listing what's missing."""
        out = self.path
        for name in self.path_params:
            if name not in values:
                raise KeyError(name)
            # Percent-encode: an agent-supplied value must not inject extra path
            # segments (../), a query (?) or a fragment (#) into the URL.
            out = out.replace("{" + name + "}", quote(str(values[name]), safe=""))
        return out

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


class Catalog:
    """Loaded, searchable set of EndpointSpec records."""

    def __init__(self, specs: list[EndpointSpec], default_host: str = "",
                 entities: Optional[Any] = None):
        self.default_host = default_host
        self.entities: Optional[Any] = entities  # EntityIndex | None — used by search()
        self._by_id: dict[str, EndpointSpec] = {}
        for s in specs:
            if not s.host:
                s.host = default_host
            if entities is not None:
                s.entity = entities.entity_of(s)
            self._by_id[s.operation_id] = s

    @classmethod
    def from_yaml(cls, path: str | Path, default_host: str = "",
                  entities: Optional[Any] = None) -> "Catalog":
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        default_host = raw.get("default_host", default_host)
        specs: list[EndpointSpec] = []
        for rec in raw.get("endpoints", []):
            specs.append(EndpointSpec(**rec))
        return cls(specs, default_host=default_host, entities=entities)

    def get(self, operation_id: str) -> Optional[EndpointSpec]:
        return self._by_id.get(operation_id)

    def all(self) -> list[EndpointSpec]:
        return list(self._by_id.values())

    def sections(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for s in self._by_id.values():
            out[s.section] = out.get(s.section, 0) + 1
        return dict(sorted(out.items()))

    def in_section(self, section: str) -> list[EndpointSpec]:
        return [s for s in self._by_id.values() if s.section == section]

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
