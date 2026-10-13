"""Credential storage for provider API keys.

Lookup order for a secret (see ``KubrickConfig.get_secret``):

1. Environment variables named by the provider field (e.g. ``ANTHROPIC_API_KEY``)
2. This store:
   - ``keyring`` backend: the OS keychain (macOS Keychain, Windows Credential
     Manager, Linux Secret Service) when the optional ``keyring`` package is
     installed and a real backend is available.
   - ``file`` backend: ``~/.kubrick/credentials.json``, each value encrypted with
     Fernet under a key derived from a random per-machine secret
     (``~/.kubrick/machine.key``, mode 0600) and the OS machine ID.

What the file backend protects against: config/credential files leaking via
backups, dotfile repos, bug reports, or being copied to another machine (the
machine ID won't match). What it does not protect against: code running as
your user on this machine, which can read the machine key too. Use the OS
keychain or environment variables when that matters.

Deleting ``machine.key`` (or moving to a new machine) makes stored credentials
undecryptable; Kubrick then asks you to authenticate again. Entries can also
expire after ``credential_max_age_days``.
"""

import base64
import hashlib
import hmac
import json
import os
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

SERVICE_NAME = "kubrick-cli"
MACHINE_KEY_FILE = "machine.key"
CREDENTIALS_FILE = "credentials.json"
_HKDF_INFO = b"kubrick-cli credentials v1"


class CredentialError(Exception):
    """Credential storage is unavailable or misconfigured."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _age_days(created_at: Optional[str]) -> Optional[float]:
    if not created_at:
        return None
    try:
        created = datetime.fromisoformat(created_at)
    except ValueError:
        return None
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - created).total_seconds() / 86400


def machine_id() -> str:
    """Best-effort stable identifier for this machine ("" if unavailable).

    Containers usually have none, which is fine: they get their own slot in
    the credential file and authenticate once.
    """
    system = platform.system()
    try:
        if system == "Linux":
            for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
                p = Path(path)
                if p.is_file():
                    value = p.read_text().strip()
                    if value:
                        return value
        elif system == "Darwin":
            out = subprocess.run(  # nosec B603 B607 - fixed command, no user input
                ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout
            for line in out.splitlines():
                if "IOPlatformUUID" in line:
                    return line.split("=")[-1].strip().strip('"')
        elif system == "Windows":
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography"
            ) as key:
                return str(winreg.QueryValueEx(key, "MachineGuid")[0])
    except Exception:
        pass  # no OS machine ID available; fall through to the fallback below
    return ""


def _hkdf_sha256(ikm: bytes, salt: bytes, info: bytes, length: int = 32) -> bytes:
    """RFC 5869 HKDF with SHA-256."""
    prk = hmac.new(salt or b"\x00" * 32, ikm, hashlib.sha256).digest()
    okm, block = b"", b""
    counter = 1
    while len(okm) < length:
        block = hmac.new(prk, block + info + bytes([counter]), hashlib.sha256).digest()
        okm += block
        counter += 1
    return okm[:length]


def _write_private(path: Path, data: bytes):
    """Write a file readable only by the current user."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass  # best effort on filesystems without POSIX permissions; content is encrypted


class _FileBackend:
    """Fernet-encrypted JSON file keyed by a machine-bound key."""

    name = "file"

    def __init__(self, kubrick_dir: Path):
        try:
            from cryptography.fernet import Fernet, InvalidToken
        except ImportError as e:  # pragma: no cover - cryptography is a hard dependency
            raise CredentialError(
                "The 'cryptography' package is required for encrypted credential storage"
            ) from e
        self._fernet_cls = Fernet
        self._invalid_token = InvalidToken
        self.key_path = kubrick_dir / MACHINE_KEY_FILE
        self.path = kubrick_dir / CREDENTIALS_FILE
        self._fernet = None
        self._slot = None

    def _cipher(self):
        if self._fernet is None:
            if not self.key_path.exists():
                _write_private(self.key_path, os.urandom(32))
            secret = self.key_path.read_bytes()
            derived = _hkdf_sha256(secret, machine_id().encode(), _HKDF_INFO)
            self._slot = hashlib.sha256(derived).hexdigest()[:16]
            self._fernet = self._fernet_cls(base64.urlsafe_b64encode(derived))
        return self._fernet

    def _load(self) -> Dict:
        if not self.path.exists():
            return {"version": 1, "slots": {}}
        try:
            data = json.loads(self.path.read_text())
        except (json.JSONDecodeError, OSError):
            return {"version": 1, "slots": {}}
        data.setdefault("slots", {})
        return data

    def _entries(self, data: Dict) -> Dict:
        self._cipher()
        return data["slots"].setdefault(self._slot, {})

    def get(self, key: str) -> Optional[Dict[str, str]]:
        entry = self._entries(self._load()).get(key)
        if not entry:
            return None
        try:
            value = self._cipher().decrypt(entry["token"].encode()).decode()
        except (self._invalid_token, KeyError, ValueError):
            return None
        return {"value": value, "created_at": entry.get("created_at")}

    def set(self, key: str, value: str):
        data = self._load()
        token = self._cipher().encrypt(value.encode()).decode()
        self._entries(data)[key] = {"token": token, "created_at": _now()}
        _write_private(self.path, json.dumps(data, indent=2).encode())

    def delete(self, key: str) -> bool:
        data = self._load()
        entries = self._entries(data)
        if key not in entries:
            return False
        del entries[key]
        _write_private(self.path, json.dumps(data, indent=2).encode())
        return True

    def keys(self) -> List[str]:
        return list(self._entries(self._load()).keys())


class _KeyringBackend:
    """OS keychain via the optional ``keyring`` package."""

    name = "keyring"

    def __init__(self, keyring_module):
        self._kr = keyring_module
        self._index_key = "__index__"

    @staticmethod
    def load() -> Optional["_KeyringBackend"]:
        """Return a backend if a usable OS keychain is available."""
        try:
            import keyring
            from keyring.backends import fail
        except ImportError:
            return None
        try:
            backend = keyring.get_keyring()
        except Exception:
            return None
        if isinstance(backend, fail.Keyring) or getattr(backend, "priority", 0) <= 0:
            return None
        if "null" in type(backend).__module__ or "chainer" in type(backend).__module__:
            # ChainerBackend with no real members, or the null backend
            if not getattr(backend, "backends", None):
                return None
        return _KeyringBackend(keyring)

    def get(self, key: str) -> Optional[Dict[str, str]]:
        raw = self._kr.get_password(SERVICE_NAME, key)
        if raw is None:
            return None
        try:
            entry = json.loads(raw)
            return {"value": entry["value"], "created_at": entry.get("created_at")}
        except (json.JSONDecodeError, KeyError, TypeError):
            return {"value": raw, "created_at": None}

    def set(self, key: str, value: str):
        self._kr.set_password(
            SERVICE_NAME, key, json.dumps({"value": value, "created_at": _now()})
        )
        index = set(self.keys())
        index.add(key)
        self._kr.set_password(SERVICE_NAME, self._index_key, json.dumps(sorted(index)))

    def delete(self, key: str) -> bool:
        try:
            self._kr.delete_password(SERVICE_NAME, key)
        except Exception:
            return False
        index = set(self.keys())
        index.discard(key)
        self._kr.set_password(SERVICE_NAME, self._index_key, json.dumps(sorted(index)))
        return True

    def keys(self) -> List[str]:
        raw = self._kr.get_password(SERVICE_NAME, self._index_key)
        try:
            return json.loads(raw) if raw else []
        except json.JSONDecodeError:
            return []


class CredentialStore:
    """Persistent secret storage with optional expiry."""

    def __init__(
        self,
        kubrick_dir: Path,
        backend: str = "auto",
        max_age_days: Optional[float] = None,
    ):
        """
        Args:
            kubrick_dir: Kubrick data directory (``~/.kubrick``)
            backend: "auto" (keychain if available, else file), "keyring", or "file"
            max_age_days: Treat stored secrets older than this as missing
        """
        self.max_age_days = max_age_days
        self._backend = None
        if backend in ("auto", "keyring"):
            self._backend = _KeyringBackend.load()
            if self._backend is None and backend == "keyring":
                raise CredentialError(
                    "credential_store is 'keyring' but no OS keychain is available "
                    "(install with: pip install 'kubrick-cli[keyring]')"
                )
        if self._backend is None:
            self._backend = _FileBackend(Path(kubrick_dir))

    @property
    def backend_name(self) -> str:
        """Which backend is in use ("keyring" or "file")."""
        return self._backend.name

    def get(self, key: str) -> Optional[str]:
        """Return a stored secret, or None if missing, undecryptable, or expired."""
        entry = self._backend.get(key)
        if not entry or self.is_expired(entry):
            return None
        return entry["value"]

    def set(self, key: str, value: str):
        """Store (or replace) a secret."""
        self._backend.set(key, value)

    def delete(self, key: str) -> bool:
        """Remove a secret; returns whether it existed."""
        return self._backend.delete(key)

    def is_expired(self, entry: Dict[str, str]) -> bool:
        """Whether an entry is older than ``max_age_days``."""
        if not self.max_age_days:
            return False
        age = _age_days(entry.get("created_at"))
        return age is not None and age > self.max_age_days

    def status(self) -> List[Dict[str, object]]:
        """Describe stored secrets without revealing them."""
        rows = []
        for key in sorted(self._backend.keys()):
            entry = self._backend.get(key)
            rows.append(
                {
                    "key": key,
                    "readable": entry is not None,
                    "created_at": entry.get("created_at") if entry else None,
                    "expired": bool(entry) and self.is_expired(entry),
                }
            )
        return rows
