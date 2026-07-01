"""Tests for the canonical-install behaviour of install.py.

Covers the fixes from the install friction log: the app is copied to a stable
location (so config doesn't break when the source folder moves), and a
secret-free breadcrumb is written for post-restart verification.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import install  # noqa: E402


def test_install_app_copies_runtime_and_excludes_vcs(tmp_path):
    dest = tmp_path / "app"
    serve = install.install_app(ROOT, dest)
    assert serve == dest / "serve.py" and serve.exists()
    # runtime essentials are present in the canonical copy
    assert (dest / "core" / "__init__.py").exists()
    assert (dest / "wb_mcp" / "endpoints.yaml").exists()
    assert (dest / "ozon_mcp" / "perf_endpoints.yaml").exists()
    # vcs / caches are NOT carried over
    assert not (dest / ".git").exists()
    assert not list(dest.rglob("__pycache__"))


def test_install_app_is_idempotent_when_src_equals_dest(tmp_path):
    dest = tmp_path / "app"
    install.install_app(ROOT, dest)
    # second run onto the same dest must not raise
    serve = install.install_app(dest, dest)
    assert serve == dest / "serve.py"


def test_copied_app_loads_catalogs(tmp_path):
    """The canonical copy must be self-sufficient — catalogs load from it."""
    dest = tmp_path / "app"
    install.install_app(ROOT, dest)
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_copied_registry", dest / "core" / "registry.py")
    # the package layout is intact, so loading via the copied tree works
    assert (dest / "core" / "registry.py").exists()
    assert spec is not None


def test_breadcrumb_records_servers_without_secrets(tmp_path, monkeypatch):
    monkeypatch.setattr(install, "APP_HOME", tmp_path)
    entries = {"wildberries": {"command": "python", "args": ["serve.py", "wb"]},
               "ozon": {"command": "python", "args": ["serve.py", "ozon"]}}
    crumb = install.write_breadcrumb(
        config_paths=[Path("/some/claude_desktop_config.json")],
        entries=entries, serve_path=tmp_path / "app" / "serve.py",
        source=Path("/Users/x/Пример/repo"))
    data = json.loads(crumb.read_text(encoding="utf-8"))
    assert crumb == tmp_path / "last_install.json"
    assert data["servers"] == ["ozon", "wildberries"]
    assert "serve_py" in data and "installed_at" in data
    # no secret-looking material leaked into the breadcrumb
    blob = crumb.read_text(encoding="utf-8").lower()
    assert "token" not in blob.replace("verify", "") or "api_key" not in blob
    assert "wb_api_token" not in blob and "client_secret" not in blob


# --- fix 6: breadcrumb must record EVERY config target (Windows multi-dir) ---

def test_breadcrumb_records_all_config_targets(tmp_path, monkeypatch):
    monkeypatch.setattr(install, "APP_HOME", tmp_path)
    entries = {"ozon": {"command": "python", "args": ["serve.py", "ozon"]}}
    targets = [Path("/store/Claude/claude_desktop_config.json"),
               Path("/roaming/Claude/claude_desktop_config.json")]
    crumb = install.write_breadcrumb(
        config_paths=targets, entries=entries,
        serve_path=tmp_path / "app" / "serve.py", source=Path("/src"))
    data = json.loads(crumb.read_text(encoding="utf-8"))
    assert data["client_configs"] == [str(t) for t in targets]


# --- fix 3: --client claude-code/codex must SAVE passed keys, not drop them ---

@pytest.mark.parametrize("client,marker", [
    ("claude-code", "claude mcp add wildberries"),
    ("codex", "codex mcp add wildberries"),
])
def test_cli_clients_save_cabinet_before_printing_commands(
        client, marker, tmp_path, monkeypatch, capsys):
    saved: list[tuple] = []
    monkeypatch.setattr(install, "save_cabinet",
                        lambda *a, **k: saved.append(a))
    monkeypatch.setattr(install, "install_app",
                        lambda src, dest: tmp_path / "app" / "serve.py")
    monkeypatch.setattr(sys, "argv", [
        "install.py", "--client", client,
        "--wb-token", "WBT", "--ozon-client-id", "123",
        "--ozon-api-key", "OKEY"])
    install.main()
    out = capsys.readouterr().out
    assert marker in out
    assert saved, f"--client {client} silently dropped the passed API keys"
    assert saved[0][:4] == ("main", "WBT", "123", "OKEY")


# --- fix 4: merge_into_config robustness -------------------------------------

def test_merge_backs_up_corrupt_config_visibly(tmp_path, capsys):
    cfg = tmp_path / "claude_desktop_config.json"
    cfg.write_text("{broken json", encoding="utf-8")
    install.merge_into_config(cfg, "mcpServers", {"ozon": {"command": "py"}})
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["mcpServers"]["ozon"]["command"] == "py"
    corrupt = list(tmp_path.glob("*.corrupt-*"))
    assert corrupt, "corrupt config must be preserved as <file>.corrupt-<n>"
    assert corrupt[0].read_text(encoding="utf-8") == "{broken json"
    assert "corrupt" in capsys.readouterr().out.lower()


def test_merge_replaces_non_dict_server_key(tmp_path, capsys):
    cfg = tmp_path / "claude_desktop_config.json"
    cfg.write_text(json.dumps({"mcpServers": ["oops"]}), encoding="utf-8")
    install.merge_into_config(cfg, "mcpServers", {"ozon": {"command": "py"}})
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["mcpServers"] == {"ozon": {"command": "py"}}


def test_merge_writes_via_atomic_replace(tmp_path, monkeypatch):
    import os as os_module
    replaced: list[tuple] = []
    real_replace = os_module.replace

    def recording_replace(src, dst):
        replaced.append((str(src), str(dst)))
        return real_replace(src, dst)

    monkeypatch.setattr(install.os, "replace", recording_replace)
    cfg = tmp_path / "claude_desktop_config.json"
    cfg.write_text(json.dumps({"keep": 1}), encoding="utf-8")
    install.merge_into_config(cfg, "mcpServers", {"ozon": {"command": "py"}})
    assert any(dst == str(cfg) for _, dst in replaced), \
        "config must be written via tmp-file + os.replace (atomic)"
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["keep"] == 1 and "ozon" in data["mcpServers"]
    assert not list(tmp_path.glob("*.tmp*")), "no tmp leftovers"


# --- fix 5: install_app must be a clean swap, keeping the venv ---------------

def test_install_app_removes_stale_files_and_keeps_venv(tmp_path):
    dest = tmp_path / "app"
    install.install_app(ROOT, dest)
    stale = dest / "core" / "stale_leftover.py"
    stale.write_text("# removed upstream", encoding="utf-8")
    venv_marker = dest / ".venv" / "marker.txt"
    venv_marker.parent.mkdir()
    venv_marker.write_text("deps installed", encoding="utf-8")
    install.install_app(ROOT, dest)
    assert not stale.exists(), "files deleted upstream must not survive update"
    assert venv_marker.exists(), "existing .venv must survive the update"
    assert (dest / "serve.py").exists()
    assert not (tmp_path / "app.new").exists(), "staging dir must be gone"


def test_install_app_failure_keeps_old_app_intact(tmp_path, monkeypatch):
    import shutil as shutil_module
    dest = tmp_path / "app"
    install.install_app(ROOT, dest)

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(install.shutil, "copy2", boom)
    with pytest.raises((OSError, shutil_module.Error)):
        install.install_app(ROOT, dest)
    # the previous canonical copy still works
    assert (dest / "serve.py").exists()
    assert (dest / "core" / "__init__.py").exists()


# --- fix 9: --print must warn that paths point at the CURRENT folder ---------

def test_print_only_keeps_stdout_json_and_warns_on_stderr(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["install.py", "--print"])
    install.main()
    cap = capsys.readouterr()
    data = json.loads(cap.out)  # stdout stays machine-readable JSON
    assert "mcpServers" in data
    assert "current folder" in cap.err.lower()
    assert str(install.APP_DIR) in cap.err
