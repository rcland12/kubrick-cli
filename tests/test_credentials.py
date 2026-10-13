"""Tests for the encrypted credential store."""

import json
import os
import stat
from datetime import datetime, timedelta, timezone

import pytest

from kubrick_cli import credentials
from kubrick_cli.credentials import CredentialStore


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(credentials, "machine_id", lambda: "machine-a")
    return CredentialStore(tmp_path, backend="file")


def test_round_trip_and_encryption(store, tmp_path):
    store.set("anthropic_api_key", "sk-secret-value")
    assert store.get("anthropic_api_key") == "sk-secret-value"
    raw = (tmp_path / "credentials.json").read_text()
    assert "sk-secret-value" not in raw
    assert store.backend_name == "file"


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions")
def test_files_are_private(store, tmp_path):
    store.set("k", "v")
    for name in ("credentials.json", "machine.key"):
        mode = stat.S_IMODE((tmp_path / name).stat().st_mode)
        assert mode == 0o600, name


def test_lost_machine_key_requires_reauth(store, tmp_path, monkeypatch):
    store.set("k", "v")
    (tmp_path / "machine.key").unlink()
    fresh = CredentialStore(tmp_path, backend="file")
    assert fresh.get("k") is None
    assert fresh.status() == []  # new key -> new, empty slot


def test_copied_to_another_machine_is_unreadable(store, tmp_path, monkeypatch):
    store.set("k", "v")
    monkeypatch.setattr(credentials, "machine_id", lambda: "machine-b")
    other = CredentialStore(tmp_path, backend="file")
    assert other.get("k") is None
    other.set("k", "v2")  # gets its own slot without clobbering machine-a's
    monkeypatch.setattr(credentials, "machine_id", lambda: "machine-a")
    assert CredentialStore(tmp_path, backend="file").get("k") == "v"


def test_expiry(tmp_path, monkeypatch):
    monkeypatch.setattr(credentials, "machine_id", lambda: "m")
    store = CredentialStore(tmp_path, backend="file", max_age_days=30)
    store.set("k", "v")
    assert store.get("k") == "v"
    data = json.loads((tmp_path / "credentials.json").read_text())
    old = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
    for slot in data["slots"].values():
        slot["k"]["created_at"] = old
    (tmp_path / "credentials.json").write_text(json.dumps(data))
    assert store.get("k") is None
    assert store.status()[0]["expired"] is True


def test_delete(store):
    store.set("k", "v")
    assert store.delete("k") is True
    assert store.get("k") is None
    assert store.delete("k") is False


def test_hkdf_matches_rfc5869_vector():
    # RFC 5869 test case 1
    ikm = bytes.fromhex("0b" * 22)
    salt = bytes.fromhex("000102030405060708090a0b0c")
    info = bytes.fromhex("f0f1f2f3f4f5f6f7f8f9")
    okm = credentials._hkdf_sha256(ikm, salt, info, 42)
    assert okm.hex() == (
        "3cb25f25faacd57a90434f64d0362f2a2d2d0a90cf1a5a4c5db02d56ecc4c5bf"
        "34007208d5b887185865"
    )


def test_keyring_backend_required_but_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(credentials._KeyringBackend, "load", staticmethod(lambda: None))
    with pytest.raises(credentials.CredentialError):
        CredentialStore(tmp_path, backend="keyring")
