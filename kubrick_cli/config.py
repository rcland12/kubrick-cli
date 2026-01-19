#!/usr/bin/env python3
"""Configuration management for Kubrick CLI."""

import json
from pathlib import Path
from typing import Any, Dict, Optional


class KubrickConfig:
    """Manages Kubrick configuration and data directories."""

    def __init__(self):
        """Initialize config manager and ensure directories exist."""
        self.kubrick_dir = Path.home() / ".kubrick"
        self.config_file = self.kubrick_dir / "config.json"
        self.conversations_dir = self.kubrick_dir / "conversations"

        # Ensure directories exist
        self._ensure_directories()

        # Load or create config
        self.config = self._load_config()

    def _ensure_directories(self):
        """Create necessary directories if they don't exist."""
        self.kubrick_dir.mkdir(exist_ok=True)
        self.conversations_dir.mkdir(exist_ok=True)

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file or create default."""
        if self.config_file.exists():
            try:
                with open(self.config_file, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                # If config is corrupted, start fresh
                return self._get_default_config()
        else:
            # Create default config
            config = self._get_default_config()
            self._save_config(config)
            return config

    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration values."""
        return {
            # Server settings
            "triton_url": "localhost:8000",
            "model_name": "llm_decoupled",
            "use_openai": False,
            "default_working_dir": None,
            # Provider settings (for future multi-provider support)
            "provider": "triton",
            "openai_api_key": None,
            "openai_model": "gpt-4",
            "anthropic_api_key": None,
            "anthropic_model": "claude-3-5-sonnet-20241022",
            # Agent loop settings
            "max_iterations": 15,
            "max_tools_per_turn": 5,
            "total_timeout_seconds": 600,
            "enable_parallel_tools": True,
            "max_parallel_workers": 3,
            # Safety settings
            "require_dangerous_command_confirmation": True,
            "tool_timeout_seconds": 30,
            "max_file_size_mb": 10,
            # Display settings
            "display_mode": "natural",  # natural, json, verbose
            "show_tool_results": True,
            "show_progress": True,
            # Task classification settings
            "enable_task_classification": True,
            "enable_planning_phase": True,
            # Conversation settings
            "auto_save_conversations": True,
            "max_conversations": 100,
        }

    def _save_config(self, config: Dict[str, Any]):
        """Save configuration to file."""
        with open(self.config_file, "w") as f:
            json.dump(config, f, indent=2)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value."""
        return self.config.get(key, default)

    def set(self, key: str, value: Any):
        """Set a configuration value and save."""
        self.config[key] = value
        self._save_config(self.config)

    def get_all(self) -> Dict[str, Any]:
        """Get all configuration values."""
        return self.config.copy()

    def save_conversation(
        self, conversation_id: str, messages: list, metadata: Dict = None
    ):
        """
        Save a conversation to disk.

        Args:
            conversation_id: Unique identifier for the conversation (e.g., timestamp)
            messages: List of message dictionaries
            metadata: Optional metadata (working_dir, triton_url, etc.)
        """
        conversation_file = self.conversations_dir / f"{conversation_id}.json"

        data = {
            "id": conversation_id,
            "messages": messages,
            "metadata": metadata or {},
        }

        with open(conversation_file, "w") as f:
            json.dump(data, f, indent=2)

        # Clean up old conversations if we exceed max
        self._cleanup_old_conversations()

    def load_conversation(self, conversation_id: str) -> Optional[Dict]:
        """
        Load a conversation from disk.

        Args:
            conversation_id: Unique identifier for the conversation

        Returns:
            Dictionary with 'id', 'messages', and 'metadata', or None if not found
        """
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

        # Sort by modification time (newest first)
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
        max_conversations = self.config.get("max_conversations", 100)

        conversations = list(self.conversations_dir.glob("*.json"))

        if len(conversations) > max_conversations:
            # Sort by modification time (oldest first)
            conversations.sort(key=lambda x: x.stat().st_mtime)

            # Delete oldest conversations
            for conv_file in conversations[
                : len(conversations) - max_conversations
            ]:
                conv_file.unlink()
