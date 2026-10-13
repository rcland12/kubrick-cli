"""Configuration management for Kubrick CLI."""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

# Keys from older versions that no longer do anything; dropped on load.
_OBSOLETE_KEYS = {
    "model_name",
    "use_openai",
    "max_tools_per_turn",
    "total_timeout_seconds",
    "enable_task_evaluator",
    "evaluator_model",
    "enable_task_classification",
    "enable_planning_phase",
    "display_mode",
    "show_tool_results",
    "show_progress",
    "clean_display",
    "context_windows",
    "default_context_window",
    "model_max_context_override",
    "context_summarization_threshold",
    "min_messages_to_keep",
    "require_dangerous_command_confirmation",
}

# Secrets older versions wrote into config.json in plaintext.
_LEGACY_SECRET_KEYS = ("openai_api_key", "anthropic_api_key")


class KubrickConfig:
    """
    Manages Kubrick configuration and data directories.

    Values resolve in this order (highest first):
    1. Session overrides (``override()``, e.g. from ``--model``) — never saved
    2. ``KUBRICK_<KEY>`` environment variables (e.g. ``KUBRICK_PROVIDER``)
    3. ``~/.kubrick/config.json``
    4. Built-in defaults
    """

    def __init__(self, skip_wizard: bool = False, kubrick_dir: Optional[Path] = None):
        """
        Initialize config manager and ensure directories exist.

        Args:
            skip_wizard: Skip setup wizard even if config doesn't exist (for tests
                and non-interactive use)
            kubrick_dir: Override the data directory (default ``~/.kubrick``,
                or ``$KUBRICK_HOME``)
        """
        if kubrick_dir is None:
            env_dir = os.environ.get("KUBRICK_HOME")
            if env_dir:
                kubrick_dir = Path(env_dir).expanduser()
            else:
                home = os.environ.get("HOME")
                kubrick_dir = (
                    Path(home).expanduser() if home else Path.home()
                ) / ".kubrick"
        self.kubrick_dir = Path(kubrick_dir)

        self.config_file = self.kubrick_dir / "config.json"
        self.conversations_dir = self.kubrick_dir / "conversations"
        self._overrides: Dict[str, Any] = {}
        self._credentials = None

        self._ensure_directories()

        self.first_run = not self.config_file.exists()
        self.config = self._load_config(skip_wizard=skip_wizard)

    def _ensure_directories(self):
        """Create necessary directories if they don't exist."""
        self.kubrick_dir.mkdir(parents=True, exist_ok=True)
        self.conversations_dir.mkdir(exist_ok=True)
        try:
            os.chmod(self.kubrick_dir, 0o700)
        except OSError:
            pass

    def _load_config(self, skip_wizard: bool = False) -> Dict[str, Any]:
        """Load configuration from file, running the setup wizard on first launch."""
        config = self._get_default_config()

        if self.config_file.exists():
            try:
                with open(self.config_file, "r") as f:
                    loaded = json.load(f)
            except (json.JSONDecodeError, IOError):
                loaded = {}
            legacy_secrets = {
                k: loaded.pop(k) for k in _LEGACY_SECRET_KEYS if loaded.get(k)
            }
            dirty = bool(legacy_secrets) or any(k in loaded for k in _OBSOLETE_KEYS)
            for key in _OBSOLETE_KEYS:
                loaded.pop(key, None)
            for key in _LEGACY_SECRET_KEYS:
                loaded.pop(key, None)
            config.update(loaded)
            self.config = config
            if legacy_secrets:
                self._migrate_legacy_secrets(legacy_secrets)
            if dirty:
                self._save_config(config)
            return config

        self.config = config
        # Configured entirely through the environment (CI, Docker): no wizard needed.
        if not skip_wizard and not os.environ.get("KUBRICK_PROVIDER"):
            from .setup_wizard import SetupWizard

            config.update(SetupWizard.run(self))
        self._save_config(config)
        return config

    def _migrate_legacy_secrets(self, secrets: Dict[str, str]):
        """Move plaintext API keys from config.json into the credential store."""
        try:
            for key, value in secrets.items():
                self.credentials.set(key, value)
            print(
                f"Moved {len(secrets)} API key(s) from config.json into the "
                f"{self.credentials.backend_name} credential store."
            )
        except Exception as e:
            print(f"Warning: could not migrate API keys to the credential store: {e}")

    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration values."""
        return {
            # Active provider (see `kubrick auth status` / setup wizard)
            "provider": "openai_compatible",
            # Provider settings live under <provider>_<field> keys; defaults come
            # from each provider's METADATA, so only non-provider settings are here.
            # Agent loop
            "max_iterations": 50,
            "tool_calling": "auto",  # auto | native | text
            "enable_parallel_tools": True,
            "max_parallel_workers": 4,
            # Permissions: default (ask for edits + commands), accept_edits, bypass
            "permission_mode": "default",
            "tool_timeout_seconds": 120,
            "max_file_size_mb": 10,
            # Credentials
            "credential_store": "auto",  # auto | keyring | file
            "credential_max_age_days": None,  # e.g. 90 to force periodic re-auth
            # Context management
            "enable_context_management": True,
            "context_window": None,  # tokens; overrides what the provider reports
            "context_usage_threshold": 0.8,  # compact at 80% of the window
            "max_output_tokens": None,  # per response; None = provider default
            "max_tool_result_chars": 30000,
            # Display
            "show_thinking": True,
            "editing_mode": "emacs",  # emacs | vi key bindings in the input box
            # Look for new releases once a day (shown at startup; never auto-installs)
            "check_for_updates": True,
            # Conversations
            "auto_save_conversations": True,
            "max_conversations": 100,
        }

    def _save_config(self, config: Dict[str, Any]):
        """Save configuration to file."""
        tmp = self.config_file.with_suffix(".json.tmp")
        with open(tmp, "w") as f:
            json.dump(config, f, indent=2)
        os.replace(tmp, self.config_file)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value (session override > env > file > default)."""
        if key in self._overrides:
            return self._overrides[key]
        env_value = os.environ.get(f"KUBRICK_{key.upper()}")
        if env_value is not None:
            return _coerce(env_value)
        return self.config.get(key, default)

    def set(self, key: str, value: Any):
        """Set a configuration value and save it to config.json."""
        self.config[key] = value
        self._overrides.pop(key, None)
        self._save_config(self.config)

    def override(self, key: str, value: Any):
        """Set a value for this session only (not saved)."""
        self._overrides[key] = value

    def get_all(self) -> Dict[str, Any]:
        """All effective configuration values (secrets are never in here)."""
        merged = dict(self.config)
        for key in list(merged):
            merged[key] = self.get(key)
        merged.update(self._overrides)
        return merged

    # --- Credentials ---------------------------------------------------------

    @property
    def credentials(self):
        """The credential store (created on first use)."""
        if self._credentials is None:
            from .credentials import CredentialStore

            self._credentials = CredentialStore(
                self.kubrick_dir,
                backend=self.get("credential_store", "auto"),
                max_age_days=self.get("credential_max_age_days"),
            )
        return self._credentials

    def get_secret(self, key: str, env_vars=()) -> Optional[str]:
        """Resolve a secret from environment variables, then the credential store."""
        for name in env_vars:
            value = os.environ.get(name)
            if value:
                return value
        return self.credentials.get(key)

    # --- Conversations -------------------------------------------------------

    def save_conversation(
        self, conversation_id: str, messages: list, metadata: Dict = None
    ):
        """
        Save a conversation to disk.

        Args:
            conversation_id: Unique identifier for the conversation (e.g., timestamp)
            messages: List of message dictionaries
            metadata: Optional metadata (working_dir, provider, etc.)
        """
        conversation_file = self.conversations_dir / f"{conversation_id}.json"

        data = {
            "id": conversation_id,
            "messages": messages,
            "metadata": metadata or {},
        }

        with open(conversation_file, "w") as f:
            json.dump(data, f, indent=2)

        self._cleanup_old_conversations()

    def load_conversation(self, conversation_id: str) -> Optional[Dict]:
        """
        Load a conversation from disk.

        Supports two modes:
        1. By ID: Loads from ~/.kubrick/conversations/<id>.json
        2. By path: Loads from absolute or relative file path

        Args:
            conversation_id: Conversation ID or file path

        Returns:
            Dictionary with 'id', 'messages', and 'metadata', or None if not found
        """
        if (
            "/" in conversation_id
            or "\\" in conversation_id
            or conversation_id.endswith(".json")
        ):
            conversation_file = Path(conversation_id).expanduser().resolve()
        else:
            conversation_file = self.conversations_dir / f"{conversation_id}.json"

        if not conversation_file.exists():
            return None

        try:
            with open(conversation_file, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

    def list_conversations(self, limit: int = None) -> list:
        """
        List all saved conversations.

        Args:
            limit: Optional limit on number of conversations to return

        Returns:
            List of conversation metadata sorted by modification time (newest first)
        """
        conversations = []

        for conv_file in self.conversations_dir.glob("*.json"):
            try:
                with open(conv_file, "r") as f:
                    data = json.load(f)

                conversations.append(
                    {
                        "id": data.get("id", conv_file.stem),
                        "metadata": data.get("metadata", {}),
                        "message_count": len(data.get("messages", [])),
                        "modified": conv_file.stat().st_mtime,
                    }
                )
            except (json.JSONDecodeError, IOError):
                continue

        conversations.sort(key=lambda x: x["modified"], reverse=True)

        if limit:
            conversations = conversations[:limit]

        return conversations

    def delete_conversation(self, conversation_id: str) -> bool:
        """
        Delete a conversation.

        Args:
            conversation_id: Unique identifier for the conversation

        Returns:
            True if deleted, False if not found
        """
        conversation_file = self.conversations_dir / f"{conversation_id}.json"

        if conversation_file.exists():
            conversation_file.unlink()
            return True
        return False

    def _cleanup_old_conversations(self):
        """Remove oldest conversations if we exceed max_conversations."""
        max_conversations = self.get("max_conversations", 100)

        conversations = list(self.conversations_dir.glob("*.json"))

        if len(conversations) > max_conversations:
            conversations.sort(key=lambda x: x.stat().st_mtime)

            for conv_file in conversations[: len(conversations) - max_conversations]:
                conv_file.unlink()


def _coerce(value: str) -> Any:
    """Interpret an environment string as JSON when possible (numbers, bools, null)."""
    try:
        return json.loads(value)
    except (json.JSONDecodeError, ValueError):
        return value
