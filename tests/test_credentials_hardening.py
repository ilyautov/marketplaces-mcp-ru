"""Hardening for the cabinet credential store — all offline.

Covers review findings:
  - the secrets file is created 0600 (no world-readable window);
  - the parent dir is 0700;
  - a corrupt cabinets.json is backed up, not silently wiped to {};
  - writes are atomic (temp file + os.replace), no partial file on the path;
  - a non-dict / unreadable root degrades gracefully instead of crashing.
"""
from __future__ import annotations

import json
import os
import stat

import pytest

from core.credentials import CredentialStore


def _store(tmp_path):
    return CredentialStore(path=tmp_path / "sub" / "cabinets.json")


# POSIX file modes don't translate to Windows (chmod is a near-no-op there; the
# store guards it with suppress(OSError) and relies on NTFS ACLs / user profile).
posix_only = pytest.mark.skipif(os.name == "nt", reason="POSIX file modes only")


@posix_only
def test_saved_file_is_0600(tmp_path):
    s = _store(tmp_path)
    s.add_cabinet("ozon", "main", {"client_id": "1", "api_key": "k"})
    mode = stat.S_IMODE(os.stat(s.path).st_mode)
    assert mode == 0o600, f"secrets file must be 0600, got {oct(mode)}"


@posix_only
def test_parent_dir_is_0700(tmp_path):
    s = _store(tmp_path)
    s.add_cabinet("ozon", "main", {"client_id": "1", "api_key": "k"})
    mode = stat.S_IMODE(os.stat(s.path.parent).st_mode)
    assert mode == 0o700, f"secrets dir must be 0700, got {oct(mode)}"


def test_corrupt_json_is_backed_up_not_wiped(tmp_path):
    s = _store(tmp_path)
    s.path.parent.mkdir(parents=True, exist_ok=True)
    s.path.write_text("{ this is not json", encoding="utf-8")

    # A read must not crash and must not silently pretend the store is empty
    # without preserving the original bytes for recovery.
    info = s.list_cabinets("ozon")
    assert info["cabinets"] == []
    backups = list(s.path.parent.glob("cabinets.json.corrupt*"))
    assert backups, "corrupt file must be backed up before being treated as empty"
    assert backups[0].read_text(encoding="utf-8") == "{ this is not json"


def test_write_is_atomic_no_leftover_temp(tmp_path):
    s = _store(tmp_path)
    s.add_cabinet("ozon", "main", {"client_id": "1", "api_key": "k"})
    s.add_cabinet("wb", "shop", {"token": "t"})
    leftovers = [p.name for p in s.path.parent.iterdir()
                 if p.name != "cabinets.json"
                 and not p.name.startswith("cabinets.json.lock")]
    assert leftovers == [], f"no temp files should remain: {leftovers}"
    data = json.loads(s.path.read_text(encoding="utf-8"))
    assert data["ozon"]["cabinets"]["main"]["client_id"] == "1"
    assert data["wb"]["cabinets"]["shop"]["token"] == "t"


def test_non_dict_root_degrades_gracefully(tmp_path):
    s = _store(tmp_path)
    s.path.parent.mkdir(parents=True, exist_ok=True)
    s.path.write_text("[1, 2, 3]", encoding="utf-8")  # valid JSON, wrong shape
    info = s.list_cabinets("ozon")
    assert info["cabinets"] == []


def test_sequential_writes_from_two_instances_preserve_both(tmp_path):
    p = tmp_path / "cabinets.json"
    a = CredentialStore(path=p)
    b = CredentialStore(path=p)
    a.add_cabinet("ozon", "one", {"client_id": "1", "api_key": "k"})
    b.add_cabinet("ozon", "two", {"client_id": "2", "api_key": "k2"})
    # b must have re-read a's write before saving, not clobbered it.
    names = CredentialStore(path=p).list_cabinets("ozon")["cabinets"]
    assert names == ["one", "two"]
