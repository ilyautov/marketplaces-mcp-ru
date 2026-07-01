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

import contextlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Callable, Optional

try:  # POSIX advisory file locking; absent on Windows.
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]

STORE_DIR = Path(os.environ.get("MARKETPLACE_MCP_HOME", Path.home() / ".marketplace-mcp"))
STORE_PATH = STORE_DIR / "cabinets.json"


class CredentialStore:
    """Reads/writes the cabinets file; resolves active credentials per service."""

    def __init__(self, path: Path = STORE_PATH):
        self.path = path

    # --- low-level io --------------------------------------------------------
    def _ensure_dir(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.path.parent, 0o700)  # this file holds live API keys
        except OSError:
            pass  # best-effort on platforms without POSIX perms

    def _load(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            raw = self.path.read_text(encoding="utf-8")
        except OSError:
            return {}
        try:
            data = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            self._backup_corrupt(raw)
            return {}
        # A valid-JSON-but-wrong-shape root (list/str/number) is unusable.
        if not isinstance(data, dict):
            self._backup_corrupt(raw)
            return {}
        return data

    def _backup_corrupt(self, raw: str) -> None:
        """Preserve an unparseable secrets file for manual recovery instead of
        letting the next write silently overwrite it with an empty store."""
        try:
            self._ensure_dir()
            n = 0
            while True:
                dest = self.path.with_name(f"{self.path.name}.corrupt-{n}")
                if not dest.exists():
                    break
                n += 1
            dest.write_text(raw, encoding="utf-8")
            with contextlib.suppress(OSError):
                os.chmod(dest, 0o600)
            print(f"[marketplace-mcp] WARNING: {self.path} was unreadable; "
                  f"backed it up to {dest} and started a fresh store. Your old "
                  f"keys are preserved in the backup for recovery.",
                  file=sys.stderr)
        except OSError:
            pass  # never let a backup failure crash a read

    def _save(self, data: dict) -> None:
        self._ensure_dir()
        # Atomic: write a 0600 temp file in the same dir, then os.replace so a
        # crash mid-write can never leave a truncated/half-written secrets file.
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent),
                                   prefix=self.path.name + ".", suffix=".tmp")
        try:
            with contextlib.suppress(OSError):
                os.chmod(tmp, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(data, ensure_ascii=False, indent=2))
            os.replace(tmp, self.path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise
        with contextlib.suppress(OSError):
            os.chmod(self.path, 0o600)

    @contextlib.contextmanager
    def _locked(self):
        """Serialize read-modify-write across the wb/ozon/ozon_perf processes
        that share one cabinets.json. Advisory flock on a sidecar lock file;
        a no-op where fcntl is unavailable (Windows) or the lock can't be taken."""
        self._ensure_dir()
        lock_path = self.path.with_name(self.path.name + ".lock")
        lock_fd = None
        try:
            if fcntl is not None:
                lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
                fcntl.flock(lock_fd, fcntl.LOCK_EX)
            yield
        finally:
            if lock_fd is not None:
                with contextlib.suppress(OSError):
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                    os.close(lock_fd)

    def _mutate(self, fn: Callable[[dict], object]) -> object:
        """Load, apply fn(data), save — all under the cross-process lock, with a
        fresh load inside the lock so a concurrent writer is never clobbered."""
        with self._locked():
            data = self._load()
            result = fn(data)
            self._save(data)
            return result

    # --- cabinet management --------------------------------------------------
    def list_cabinets(self, service: str) -> dict:
        svc = self._load().get(service, {})
        return {
            "active": svc.get("active"),
            "cabinets": sorted((svc.get("cabinets") or {}).keys()),
        }

    def add_cabinet(self, service: str, name: str, creds: dict,
                    make_active: bool = True) -> None:
        def apply(data: dict) -> None:
            svc = data.setdefault(service, {"active": None, "cabinets": {}})
            svc["cabinets"][name] = creds
            if make_active or not svc.get("active"):
                svc["active"] = name
        self._mutate(apply)

    def remove_cabinet(self, service: str, name: str) -> bool:
        def apply(data: dict) -> bool:
            svc = data.get(service, {})
            cabs = svc.get("cabinets", {})
            if name not in cabs:
                return False
            del cabs[name]
            if svc.get("active") == name:
                svc["active"] = next(iter(cabs), None)
            return True
        return bool(self._mutate(apply))

    def set_active(self, service: str, name: str) -> bool:
        def apply(data: dict) -> bool:
            svc = data.get(service, {})
            if name not in (svc.get("cabinets") or {}):
                return False
            svc["active"] = name
            return True
        return bool(self._mutate(apply))

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
