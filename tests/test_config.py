#!/usr/bin/env python3
"""Test script for Kubrick configuration system."""

from datetime import datetime
from kubrick_cli.config import KubrickConfig


def test_config():
    """Test configuration management."""
    print("\n" + "="*60)
    print("Testing Kubrick Configuration System")
    print("="*60 + "\n")

    # Initialize config
    print("1. Initializing config...")
    config = KubrickConfig(skip_wizard=True)
    print(f"   ✓ Config directory: {config.kubrick_dir}")
    print(f"   ✓ Config file: {config.config_file}")
    print(f"   ✓ Conversations dir: {config.conversations_dir}")

    # Test getting config values
    print("\n2. Testing config values...")
    triton_url = config.get("triton_url")
    print(f"   ✓ triton_url: {triton_url}")
    print(f"   ✓ model_name: {config.get('model_name')}")
    print(f"   ✓ auto_save_conversations: {config.get('auto_save_conversations')}")

    # Test setting config values
    print("\n3. Testing config updates...")
    config.set("test_key", "test_value")
    print(f"   ✓ Set test_key = test_value")
    assert config.get("test_key") == "test_value"
    print(f"   ✓ Verified test_key = {config.get('test_key')}")

    # Test saving conversation
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

    # Test loading conversation
    print("\n5. Testing conversation loading...")
    loaded = config.load_conversation(conv_id)
    assert loaded is not None
    print(f"   ✓ Loaded conversation: {conv_id}")
    print(f"   ✓ Messages count: {len(loaded['messages'])}")
    print(f"   ✓ Metadata: {loaded['metadata']}")

    # Test listing conversations
    print("\n6. Testing conversation listing...")
    conversations = config.list_conversations(limit=5)
    print(f"   ✓ Found {len(conversations)} conversations")
    for conv in conversations[:3]:
        print(f"      - {conv['id']}: {conv['message_count']} messages")

    # Test deleting conversation
    print("\n7. Testing conversation deletion...")
    result = config.delete_conversation(conv_id)
    assert result is True
    print(f"   ✓ Deleted conversation: {conv_id}")

    # Verify deletion
    loaded = config.load_conversation(conv_id)
    assert loaded is None
    print(f"   ✓ Verified deletion")

    # Test all config values
    print("\n8. Testing get_all()...")
    all_config = config.get_all()
    print(f"   ✓ Got {len(all_config)} config values:")
    for key, value in all_config.items():
        print(f"      - {key}: {value}")

    print("\n" + "="*60)
    print("All tests PASSED! ✓")
    print("="*60 + "\n")
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
