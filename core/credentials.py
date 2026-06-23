"""Multi-cabinet credential store.

Built for a teaching product: every student installs the same servers and points
them at their own marketplace cabinet(s). One person may run several cabinets
(e.g. two Ozon shops) and switch between them from chat.

Storage: ``~/.marketplace-mcp/cabinets.json`` (outside the repo, chmod 600).
Shape::

    {
      "ozon": {
        "active": "main",
        "cabinets": {
          "main":   {"client_id": "...", "api_key": "..."},
          "second": {"client_id": "...", "api_key": "..."}
        }
      },
      "wb": {"active": "main", "cabinets": {"main": {"token": "..."}}}
    }

Resolution order for the active credentials of a service:
  1. the active cabinet in cabinets.json, if any;
  2. else environment variables (back-compat: an env-only install behaves like a
     single cabinet named "env").

Keys live in a local file the student controls — same trust model as the Claude
desktop config. Never commit this file.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

STORE_DIR = Path(os.environ.get("MARKETPLACE_MCP_HOME", Path.home() / ".marketplace-mcp"))
STORE_PATH = STORE_DIR / "cabinets.json"


class CredentialStore:
    """Reads/writes the cabinets file; resolves active credentials per service."""

    def __init__(self, path: Path = STORE_PATH):
        self.path = path

    # --- low-level io --------------------------------------------------------
    def _load(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8")) or {}
        except json.JSONDecodeError:
            return {}

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                             encoding="utf-8")
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass  # best-effort on platforms without POSIX perms

    # --- cabinet management --------------------------------------------------
    def list_cabinets(self, service: str) -> dict:
        svc = self._load().get(service, {})
        return {
            "active": svc.get("active"),
            "cabinets": sorted((svc.get("cabinets") or {}).keys()),
        }

    def add_cabinet(self, service: str, name: str, creds: dict,
                    make_active: bool = True) -> None:
        data = self._load()
        svc = data.setdefault(service, {"active": None, "cabinets": {}})
        svc["cabinets"][name] = creds
        if make_active or not svc.get("active"):
            svc["active"] = name
        self._save(data)

    def remove_cabinet(self, service: str, name: str) -> bool:
        data = self._load()
        svc = data.get(service, {})
        cabs = svc.get("cabinets", {})
        if name not in cabs:
            return False
        del cabs[name]
        if svc.get("active") == name:
            svc["active"] = next(iter(cabs), None)
        self._save(data)
        return True

    def set_active(self, service: str, name: str) -> bool:
        data = self._load()
        svc = data.get(service, {})
        if name not in (svc.get("cabinets") or {}):
            return False
        svc["active"] = name
        self._save(data)
        return True

    # --- resolution ----------------------------------------------------------
    def resolve(self, service: str, fields: list[str],
                env_map: dict[str, str]) -> tuple[dict, str]:
        """Return (creds, source). Active cabinet wins; else env; else empty.

        creds always has every requested field (possibly empty string).
        source is the cabinet name, "env", or "none".
        """
        svc = self._load().get(service, {})
        active = svc.get("active")
        cabs = svc.get("cabinets") or {}
        if active and active in cabs:
            stored = cabs[active]
            creds = {f: stored.get(f, "") for f in fields}
            if all(creds[f] for f in fields):
                return creds, active
        # env fallback
        env_creds = {f: os.environ.get(env_map.get(f, ""), "") for f in fields}
        if all(env_creds[f] for f in fields):
            return env_creds, "env"
        # partial / nothing — return whatever we have, mark source
        merged = {f: (cabs.get(active, {}).get(f, "") if active else "")
                     or env_creds.get(f, "") for f in fields}
        source = active if (active and active in cabs) else (
            "env" if any(env_creds.values()) else "none")
        return merged, source

    def missing(self, service: str, fields: list[str],
                env_map: dict[str, str]) -> list[str]:
        creds, _ = self.resolve(service, fields, env_map)
        return [f for f in fields if not creds.get(f)]
