"""Pytest configuration and shared fixtures."""

import tempfile
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Keep every test away from the real ~/.kubrick and credential env vars."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("KUBRICK_HOME", raising=False)
    for name in (
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "OPENAI_COMPATIBLE_API_KEY",
        "KUBRICK_PROVIDER",
        "KUBRICK_CREDENTIAL_STORE",
        "KUBRICK_ASCII",
        "KUBRICK_SIMPLE_UI",
    ):
        monkeypatch.delenv(name, raising=False)
    # Never touch the developer's real OS keychain.
    monkeypatch.setenv("KUBRICK_CREDENTIAL_STORE", "file")
    return home


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir).resolve()


@pytest.fixture
def sample_messages():
    """Sample message list for testing LLM interactions."""
    return [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello, how are you?"},
    ]


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "unit: Mark test as a unit test (no external dependencies)"
    )
    config.addinivalue_line(
        "markers",
        "integration: Mark test as an integration test (may use external services)",
    )
    config.addinivalue_line("markers", "slow: Mark test as slow running")
