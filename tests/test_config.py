"""Tests for KubrickConfig."""

import json

from kubrick_cli.config import KubrickConfig


def test_defaults_and_first_run(isolated_home):
    config = KubrickConfig(skip_wizard=True)
    assert config.kubrick_dir == isolated_home / ".kubrick"
    assert config.config_file.exists()
    assert config.get("permission_mode") == "default"
    assert config.get("tool_calling") == "auto"


def test_env_override_and_coercion(monkeypatch):
    config = KubrickConfig(skip_wizard=True)
    monkeypatch.setenv("KUBRICK_MAX_ITERATIONS", "7")
    monkeypatch.setenv("KUBRICK_TRITON_URL", "gpu-box:8000")
    assert config.get("max_iterations") == 7
    assert config.get("triton_url") == "gpu-box:8000"


def test_session_override_is_not_saved():
    config = KubrickConfig(skip_wizard=True)
    config.override("provider", "anthropic")
    assert config.get("provider") == "anthropic"
    saved = json.loads(config.config_file.read_text())
    assert saved["provider"] != "anthropic"


def test_set_persists():
    config = KubrickConfig(skip_wizard=True)
    config.set("max_iterations", 12)
    assert KubrickConfig(skip_wizard=True).get("max_iterations") == 12


def test_legacy_plaintext_keys_migrate_to_store(isolated_home):
    kdir = isolated_home / ".kubrick"
    kdir.mkdir()
    (kdir / "config.json").write_text(
        json.dumps(
            {
                "provider": "anthropic",
                "anthropic_api_key": "sk-ant-legacy",
                "enable_task_classification": True,
            }
        )
    )
    config = KubrickConfig(skip_wizard=True)
    saved = json.loads(config.config_file.read_text())
    assert "anthropic_api_key" not in saved
    assert "enable_task_classification" not in saved
    assert config.get_secret("anthropic_api_key") == "sk-ant-legacy"
    assert "sk-ant-legacy" not in (kdir / "credentials.json").read_text()


def test_get_secret_prefers_env(monkeypatch):
    config = KubrickConfig(skip_wizard=True)
    config.credentials.set("openai_api_key", "stored")
    assert config.get_secret("openai_api_key", ["OPENAI_API_KEY"]) == "stored"
    monkeypatch.setenv("OPENAI_API_KEY", "from-env")
    assert config.get_secret("openai_api_key", ["OPENAI_API_KEY"]) == "from-env"


def test_conversation_round_trip(tmp_path):
    config = KubrickConfig(skip_wizard=True)
    messages = [{"role": "user", "content": "hi"}]
    config.save_conversation("abc", messages, {"working_dir": "/x"})
    assert config.load_conversation("abc")["messages"] == messages
    assert config.list_conversations()[0]["id"] == "abc"
    path = tmp_path / "conv.json"
    path.write_text(json.dumps({"id": "ext", "messages": messages}))
    assert config.load_conversation(str(path))["id"] == "ext"
    assert config.delete_conversation("abc") is True
    assert config.load_conversation("abc") is None
