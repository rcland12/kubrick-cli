"""Pytest configuration and shared fixtures."""

import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        yield workspace


@pytest.fixture
def sample_messages():
    """Sample message list for testing LLM interactions."""
    return [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello, how are you?"},
    ]


@pytest.fixture
def mock_llm_response():
    """Mock LLM response for testing."""
    return "I'm doing great! How can I help you today?"


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
