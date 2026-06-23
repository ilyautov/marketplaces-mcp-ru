"""Workflow layer — curated recipes that turn raw endpoints into outcomes.

A workflow is a named, step-by-step plan an agent follows to answer a real
seller question ("which products are about to run out?", "is my pricing
competitive?"). Each step names a catalog operation_id and explains why; the
workflow also carries `interpret` guidance and `common_mistakes`.

Recipes live in `{service}/workflows.yaml`. Two tools expose them:
    {svc}_list_workflows  — browse available recipes
    {svc}_get_workflow    — full plan for one recipe
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import yaml
from mcp.server.fastmcp import FastMCP


def _j(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, default=str)


class Workflows:
    def __init__(self, recipes: list[dict]):
        self._by_name = {r["name"]: r for r in recipes}

    @classmethod
    def from_yaml(cls, path: str | Path) -> "Workflows":
        p = Path(path)
        if not p.exists():
            return cls([])
        raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        return cls(raw.get("workflows", []))

    def names(self) -> list[dict]:
        return [{"name": r["name"], "category": r.get("category", ""),
                 "when_to_use": r.get("when_to_use", "")}
                for r in self._by_name.values()]

    def get(self, name: str) -> Optional[dict]:
        return self._by_name.get(name)


def register_workflow_tools(mcp: FastMCP, *, svc: str, workflows: Workflows) -> None:
    @mcp.tool(
        name=f"{svc}_list_workflows",
        annotations={"title": f"{svc.upper()} list workflows",
                     "readOnlyHint": True, "openWorldHint": False},
    )
    async def list_workflows() -> str:
        """List ready-made analytical workflows (recipes) for this marketplace.

        Returns JSON: [{name, category, when_to_use}]. Use {svc}_get_workflow
        to fetch the full step-by-step plan for one.
        """
        return _j({"workflows": workflows.names()})

    @mcp.tool(
        name=f"{svc}_get_workflow",
        annotations={"title": f"{svc.upper()} get workflow",
                     "readOnlyHint": True, "openWorldHint": False},
    )
    async def get_workflow(name: str) -> str:
        """Return the full plan for one workflow: ordered steps (each naming a
        catalog operation_id and why), interpretation guidance, and common
        mistakes to avoid.

        Args:
            name: workflow name (see {svc}_list_workflows).
        """
        wf = workflows.get(name)
        if not wf:
            return _j({"error": "not_found", "name": name,
                       "available": [w["name"] for w in workflows.names()]})
        return _j(wf)
