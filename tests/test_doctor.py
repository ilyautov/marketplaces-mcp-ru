"""``doctor`` runs in a clean environment and tells the truth about keys.

Runs in a subprocess so the credential store location (read at import time
from MARKETPLACE_MCP_HOME) can be pointed at an empty temp dir, and so a
stray real cabinet on the developer's machine can never leak into the result.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core import doctor  # noqa: E402

_CRED_VARS = ("WB_API_TOKEN", "OZON_CLIENT_ID", "OZON_API_KEY",
              "OZON_PERF_CLIENT_ID", "OZON_PERF_CLIENT_SECRET")


def _run(tmp_path, extra_env=None, *args):
    env = {k: v for k, v in os.environ.items() if k not in _CRED_VARS}
    env["MARKETPLACE_MCP_HOME"] = str(tmp_path / "home")
    env["PYTHONPATH"] = str(ROOT)
    env.update(extra_env or {})
    return subprocess.run(
        [sys.executable, "-m", "core.doctor", *args],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=120,
    )


def test_no_credentials_exits_1_but_reports_every_service(tmp_path):
    proc = _run(tmp_path, None, "--json")
    assert proc.returncode == 1, proc.stderr
    reports = json.loads(proc.stdout)
    assert [r["service"] for r in reports] == ["wb", "ozon", "ozon_perf"]
    for r in reports:
        assert not r["error"], r
        assert r["tools"] > 0 and r["methods"] > 0
        assert r["ready"] is False and r["source"] == "none"
        assert r["live"] is None  # not requested
    wb = reports[0]
    assert wb["env_names"] == ["WB_API_TOKEN"]


def test_env_keys_make_service_ready_without_network(tmp_path):
    proc = _run(tmp_path, {"WB_API_TOKEN": "dummy-token"})
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = proc.stdout
    assert "Wildberries" in out and "Ozon Seller" in out and "Ozon Performance" in out
    assert "dummy-token" not in out  # never echo a secret
    assert "env" in out
    assert "none — set OZON_CLIENT_ID, OZON_API_KEY" in out


def test_table_and_exit_code_logic_offline():
    ok = doctor.ServiceReport("wb", "Wildberries", tools=19, methods=307,
                              ready=True, source="main")
    none = doctor.ServiceReport("ozon", "Ozon Seller", tools=19, methods=441,
                                env_names=["OZON_CLIENT_ID", "OZON_API_KEY"])
    broken = doctor.ServiceReport("ozon_perf", "Ozon Performance", error="ImportError: x")

    assert doctor.exit_code([ok, none], live=False) == 0
    assert doctor.exit_code([none], live=False) == 1
    assert doctor.exit_code([ok, broken], live=False) == 1

    ok_fail = doctor.ServiceReport("wb", "Wildberries", ready=True, source="env",
                                   live="fail", live_detail="auth: 401")
    assert doctor.exit_code([ok_fail], live=True) == 1
    assert doctor.exit_code([ok], live=False) == 0

    text = doctor.format_table([ok, none, broken], live=False)
    assert 'cabinet "main"' in text
    assert "none — set OZON_CLIENT_ID, OZON_API_KEY" in text
    assert "! Ozon Performance: ImportError: x" in text
