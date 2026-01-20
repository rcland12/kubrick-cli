#!/usr/bin/env python3
"""Test script for Kubrick configuration system."""

from datetime import datetime
from kubrick_cli.config import KubrickConfig


def test_config():
    """Test configuration management."""
    print("\n" + "=" * 60)
    print("Testing Kubrick Configuration System")
    print("=" * 60 + "\n")

    print("1. Initializing config...")
    config = KubrickConfig(skip_wizard=True)
    print(f"   ✓ Config directory: {config.kubrick_dir}")
    print(f"   ✓ Config file: {config.config_file}")
    print(f"   ✓ Conversations dir: {config.conversations_dir}")

    print("\n2. Testing config values...")
    triton_url = config.get("triton_url")
    print(f"   ✓ triton_url: {triton_url}")
    print(f"   ✓ model_name: {config.get('model_name')}")
    print(f"   ✓ auto_save_conversations: {config.get('auto_save_conversations')}")

    print("\n3. Testing config updates...")
    config.set("test_key", "test_value")
    print("   ✓ Set test_key = test_value")
    assert config.get("test_key") == "test_value"
    print(f"   ✓ Verified test_key = {config.get('test_key')}")

    print("\n4. Testing conversation persistence...")
    conv_id = datetime.now().strftime("%Y%m%d_%H%M%S_test")
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello!"},
        {"role": "assistant", "content": "Hi! How can I help you?"},
    ]
    metadata = {
        "working_dir": "/test/path",
        "triton_url": "localhost:8000",
    }

    config.save_conversation(conv_id, messages, metadata)
    print(f"   ✓ Saved conversation: {conv_id}")

    print("\n5. Testing conversation loading...")
    loaded = config.load_conversation(conv_id)
    assert loaded is not None
    print(f"   ✓ Loaded conversation: {conv_id}")
    print(f"   ✓ Messages count: {len(loaded['messages'])}")
    print(f"   ✓ Metadata: {loaded['metadata']}")

    print("\n6. Testing conversation listing...")
    conversations = config.list_conversations(limit=5)
    print(f"   ✓ Found {len(conversations)} conversations")
    for conv in conversations[:3]:
        print(f"      - {conv['id']}: {conv['message_count']} messages")

    print("\n7. Testing conversation deletion...")
    result = config.delete_conversation(conv_id)
    assert result is True
    print(f"   ✓ Deleted conversation: {conv_id}")

    loaded = config.load_conversation(conv_id)
    assert loaded is None
    print("   ✓ Verified deletion")

    print("\n8. Testing conversation loading from file path...")
    import tempfile
    import json

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        test_conv_data = {
            "id": "external_test",
            "messages": [
                {"role": "user", "content": "Test from file"},
                {"role": "assistant", "content": "Response from file"},
            ],
            "metadata": {"source": "external_file"},
        }
        json.dump(test_conv_data, f)
        temp_file_path = f.name

    print(f"   ✓ Created temp conversation file: {temp_file_path}")

    loaded_from_path = config.load_conversation(temp_file_path)
    assert loaded_from_path is not None
    assert loaded_from_path["id"] == "external_test"
    assert len(loaded_from_path["messages"]) == 2
    print("   ✓ Loaded conversation from file path")
    print(f"   ✓ Messages: {len(loaded_from_path['messages'])}")

    from pathlib import Path

    home_relative = Path(temp_file_path).expanduser()
    loaded_home = config.load_conversation(str(home_relative))
    assert loaded_home is not None
    print("   ✓ Loaded using expanded path")

    Path(temp_file_path).unlink()
    print("   ✓ Cleaned up temp file")

    print("\n9. Testing get_all()...")
    all_config = config.get_all()
    print(f"   ✓ Got {len(all_config)} config values:")
    for key, value in list(all_config.items())[:5]:
        print(f"      - {key}: {value}")
    print(f"      ... and {len(all_config) - 5} more")

    print("\n" + "=" * 60)
    print("All tests PASSED! ✓")
    print("=" * 60 + "\n")
    print(f"Configuration is stored at: {config.config_file}")
    print(f"Conversations are stored at: {config.conversations_dir}")
    print("")


if __name__ == "__main__":
    import sys

    try:
        success = test_config()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback

        print(traceback.format_exc())
        sys.exit(1)
