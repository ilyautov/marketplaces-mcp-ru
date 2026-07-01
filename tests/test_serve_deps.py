"""Tests for the dependency bootstrap in serve.py (_ensure_deps).

Covers the offline-start fix: a machine with a ready venv must start WITHOUT
running pip (site-packages are injected and checked FIRST), the deps-stamp
fast path, pinned upper bounds, and venv recreation when the venv belongs to
another Python version. All tests are offline — subprocess.run is stubbed.
"""
from __future__ import annotations

import os
import sys
import venv as venv_module
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import serve  # noqa: E402


def _write_layout(venv_dir: Path) -> Path:
    """Create the interpreter + site-packages layout serve.py expects on THIS
    OS (Windows uses Scripts/python.exe + Lib/site-packages; POSIX uses
    bin/python + lib/pythonX.Y/site-packages). Returns the site-packages dir."""
    if os.name == "nt":
        (venv_dir / "Scripts").mkdir(parents=True, exist_ok=True)
        (venv_dir / "Scripts" / "python.exe").write_text("", encoding="utf-8")
        sp = venv_dir / "Lib" / "site-packages"
    else:
        (venv_dir / "bin").mkdir(parents=True, exist_ok=True)
        (venv_dir / "bin" / "python").write_text("", encoding="utf-8")
        sp = venv_dir / "lib" / "python3.11" / "site-packages"
    sp.mkdir(parents=True, exist_ok=True)
    return sp


def _make_venv(tmp_path: Path, stamp: str | None = None) -> tuple[Path, Path]:
    """Create a fake, OS-correct venv layout and return (venv_dir, site_packages)."""
    venv_dir = tmp_path / ".venv"
    sp = _write_layout(venv_dir)
    if stamp is not None:
        (venv_dir / "deps-stamp.txt").write_text(stamp, encoding="utf-8")
    return venv_dir, sp


def test_deps_have_upper_version_bounds():
    """A future mcp 2.x / httpx 1.x must not silently break old installs."""
    assert serve.DEPS == ["mcp>=1.2,<2", "httpx>=0.27,<1", "pyyaml>=6.0,<7"]


def test_offline_start_with_ready_venv_runs_no_pip(tmp_path, monkeypatch):
    """CRITICAL: venv already provisioned + stamp up to date -> no pip at all.

    site-packages must be injected into sys.path BEFORE the import check, so
    deps that live only inside the venv are found without any network access.
    """
    venv_dir, sp = _make_venv(tmp_path, stamp="\n".join(serve.DEPS))
    monkeypatch.setattr(serve, "VENV", venv_dir)
    # deps are importable ONLY once the venv's site-packages is on sys.path
    monkeypatch.setattr(serve, "_deps_importable",
                        lambda: str(sp) in sys.path)
    monkeypatch.setattr(
        serve.subprocess, "run",
        lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("pip must NOT run when the venv is ready (offline)")))
    assert serve._ensure_deps() is True


def test_install_command_has_no_pip_upgrade(tmp_path, monkeypatch):
    """`--upgrade pip` needs the network even when deps are cached — drop it."""
    venv_dir, sp = _make_venv(tmp_path)  # venv exists, no stamp, empty sp
    monkeypatch.setattr(serve, "VENV", venv_dir)
    state = {"installed": False}
    monkeypatch.setattr(serve, "_deps_importable", lambda: state["installed"])
    calls: list[list[str]] = []

    def fake_run(cmd, **kw):
        calls.append([str(c) for c in cmd])
        state["installed"] = True

    monkeypatch.setattr(serve.subprocess, "run", fake_run)
    assert serve._ensure_deps() is True
    assert calls, "pip install expected on first provisioning"
    assert "--upgrade" not in calls[0]


def test_stamp_written_after_successful_install(tmp_path, monkeypatch):
    venv_dir, sp = _make_venv(tmp_path)
    monkeypatch.setattr(serve, "VENV", venv_dir)
    state = {"installed": False}
    monkeypatch.setattr(serve, "_deps_importable", lambda: state["installed"])

    def fake_run(cmd, **kw):
        state["installed"] = True

    monkeypatch.setattr(serve.subprocess, "run", fake_run)
    assert serve._ensure_deps() is True
    stamp = venv_dir / "deps-stamp.txt"
    assert stamp.exists()
    assert stamp.read_text(encoding="utf-8").strip() == "\n".join(serve.DEPS)


def test_changed_deps_trigger_reinstall_and_stamp_update(tmp_path, monkeypatch):
    """Stale stamp (DEPS list changed in a new release) -> reinstall once."""
    venv_dir, sp = _make_venv(tmp_path, stamp="mcp>=1.0  # old pins")
    monkeypatch.setattr(serve, "VENV", venv_dir)
    monkeypatch.setattr(serve, "_deps_importable", lambda: True)
    calls: list[list[str]] = []
    monkeypatch.setattr(serve.subprocess, "run",
                        lambda cmd, **kw: calls.append([str(c) for c in cmd]))
    assert serve._ensure_deps() is True
    assert len(calls) == 1, "stale stamp must trigger exactly one pip install"
    assert (venv_dir / "deps-stamp.txt").read_text(
        encoding="utf-8").strip() == "\n".join(serve.DEPS)


def test_offline_reinstall_failure_tolerated_when_deps_import(tmp_path, monkeypatch):
    """Stamp is stale but pip is unreachable (offline): server must still start
    because the old deps DO import."""
    venv_dir, sp = _make_venv(tmp_path, stamp="old-pins")
    monkeypatch.setattr(serve, "VENV", venv_dir)
    monkeypatch.setattr(serve, "_deps_importable", lambda: True)

    def fake_run(cmd, **kw):
        raise OSError("network unreachable")

    monkeypatch.setattr(serve.subprocess, "run", fake_run)
    assert serve._ensure_deps() is True


def test_broken_venv_is_recreated_once(tmp_path, monkeypatch):
    """venv from another Python version: install 'succeeds' but import still
    fails -> recreate the venv (clear=True) and install again."""
    venv_dir, sp = _make_venv(tmp_path)
    monkeypatch.setattr(serve, "VENV", venv_dir)
    state = {"cleared": False, "pip_after_clear": False}
    monkeypatch.setattr(serve, "_deps_importable",
                        lambda: state["pip_after_clear"])

    class FakeBuilder:
        def __init__(self, with_pip=False, clear=False, **kw):
            self.clear = clear

        def create(self, path):
            path = Path(path)
            if self.clear:
                state["cleared"] = True
            _write_layout(path)

    monkeypatch.setattr(venv_module, "EnvBuilder", FakeBuilder)

    def fake_run(cmd, **kw):
        if state["cleared"]:
            state["pip_after_clear"] = True

    monkeypatch.setattr(serve.subprocess, "run", fake_run)
    assert serve._ensure_deps() is True
    assert state["cleared"], "venv must be recreated with clear=True"


def test_gives_up_after_one_recreate(tmp_path, monkeypatch):
    """If even a fresh venv doesn't make deps importable, fail (no infinite loop)."""
    venv_dir, sp = _make_venv(tmp_path)
    monkeypatch.setattr(serve, "VENV", venv_dir)
    monkeypatch.setattr(serve, "_deps_importable", lambda: False)
    creates = {"clear": 0}

    class FakeBuilder:
        def __init__(self, with_pip=False, clear=False, **kw):
            self.clear = clear

        def create(self, path):
            if self.clear:
                creates["clear"] += 1
            _write_layout(Path(path))

    monkeypatch.setattr(venv_module, "EnvBuilder", FakeBuilder)
    monkeypatch.setattr(serve.subprocess, "run", lambda *a, **k: None)
    assert serve._ensure_deps() is False
    assert creates["clear"] <= 1
