"""AWS credentials in .env form (``KEY=VALUE`` / ``export KEY=VALUE``) for Bedrock.

Many organizations hand out temporary keys as a block of environment variables. These
helpers parse such blocks (pasted or from a file), and describe when they expire.
"""

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

# The variables Kubrick understands; others in a pasted block are ignored.
KNOWN_KEYS = (
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AWS_REGION",
    "AWS_DEFAULT_REGION",
    "AWS_BEARER_TOKEN_BEDROCK",
    "AWS_TOKEN_EXPIRATION",
    "AWS_CREDENTIAL_EXPIRATION",
    "AWS_SESSION_EXPIRATION",
    "AWS_EXPIRATION",
)
_EXPIRY_KEYS = KNOWN_KEYS[6:]

# KEY=VALUE, optionally after "export" or "set", with optional quotes. Matched anywhere so
# a block pasted onto one line still parses.
_ASSIGNMENT = re.compile(
    r"(?:\b(?:export|set)\s+)?\b([A-Z][A-Z0-9_]*)\s*=\s*"
    r"(\"[^\"]*\"|'[^']*'|[^\s\"';]+)"
)


def parse_env_text(text: str) -> Dict[str, str]:
    """AWS variables from ``KEY=VALUE`` lines (``export``/``set`` prefixes and quotes ok)."""
    values: Dict[str, str] = {}
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        for key, value in _ASSIGNMENT.findall(stripped):
            if key in KNOWN_KEYS:
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1]
                values[key] = value.strip()
    return values


def load_env_file(path: str) -> Dict[str, str]:
    """Parse an env file; missing or unreadable files give an empty dict."""
    try:
        return parse_env_text(Path(path).expanduser().read_text())
    except OSError:
        return {}


def write_env_file(path: str, values: Dict[str, str]):
    """Write credentials as ``KEY=VALUE`` lines, readable only by the owner."""
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(f"{k}={values[k]}\n" for k in KNOWN_KEYS if values.get(k))
    fd = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(body)
    try:
        os.chmod(target, 0o600)
    except OSError:
        pass


def is_usable(values: Dict[str, str]) -> bool:
    """Whether ``values`` can authenticate (key pair or a Bedrock API key)."""
    return bool(
        (values.get("AWS_ACCESS_KEY_ID") and values.get("AWS_SECRET_ACCESS_KEY"))
        or values.get("AWS_BEARER_TOKEN_BEDROCK")
    )


def region_of(values: Dict[str, str]) -> Optional[str]:
    return values.get("AWS_REGION") or values.get("AWS_DEFAULT_REGION") or None


def expiration_of(values: Dict[str, str]) -> Optional[datetime]:
    """When the credentials expire, if the block says (ISO 8601 or epoch seconds)."""
    for key in _EXPIRY_KEYS:
        raw = (values.get(key) or "").strip()
        if not raw:
            continue
        try:
            if raw.isdigit():
                return datetime.fromtimestamp(int(raw), tz=timezone.utc)
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except (ValueError, OverflowError, OSError):
            continue
    return None


def seconds_left(values: Dict[str, str]) -> Optional[float]:
    expiry = expiration_of(values)
    if expiry is None:
        return None
    return (expiry - datetime.now(timezone.utc)).total_seconds()


def describe_expiry(values: Dict[str, str]) -> Optional[str]:
    """``"expires in 3h 12m"`` / ``"expired 5m ago"``, or None if unknown."""
    left = seconds_left(values)
    if left is None:
        return None
    minutes = int(abs(left) // 60)
    span = f"{minutes // 60}h {minutes % 60}m" if minutes >= 60 else f"{minutes}m"
    return f"expires in {span}" if left > 0 else f"expired {span} ago"


def to_json(values: Dict[str, str]) -> str:
    return json.dumps({k: v for k, v in values.items() if k in KNOWN_KEYS and v})


def from_json(raw: Optional[str]) -> Dict[str, str]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        return parse_env_text(raw)
    return {k: str(v) for k, v in data.items() if k in KNOWN_KEYS} if data else {}
