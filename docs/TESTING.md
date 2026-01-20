# Testing Guide

This document describes the testing infrastructure for Kubrick CLI.

## Overview

Kubrick CLI uses `pytest` for testing. All tests are located in the `tests/` directory and are designed to run in CI/CD environments (like GitHub Actions) without requiring external dependencies like a running Triton server.

## Test Structure

```
tests/
├── conftest.py                      # Shared fixtures and pytest configuration
├── test_config.py                   # Configuration management tests (existing)
├── test_tool_calling.py             # Tool call parsing tests (existing)
├── test_tool_executor.py            # ToolExecutor unit tests (NEW)
├── test_safety.py                   # SafetyManager unit tests (NEW)
├── test_completion_detector.py      # CompletionDetector unit tests (NEW)
└── test_triton_client_unit.py       # TritonLLMClient unit tests with mocks (NEW)
```

## Running Tests

### Install Development Dependencies

First, install the package with development dependencies:

```bash
pip install -e ".[dev]"
```

This installs:

- pytest (testing framework)
- pytest-cov (coverage reporting)
- pytest-mock (mocking utilities)
- black (code formatter)
- flake8 (linter)

### Run All Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run with coverage report
pytest --cov=kubrick_cli --cov-report=term-missing
```

### Run Specific Test Files

```bash
# Run only tool executor tests
pytest tests/test_tool_executor.py

# Run only safety tests
pytest tests/test_safety.py

# Run only completion detector tests
pytest tests/test_completion_detector.py
```

### Run Specific Test Classes or Methods

```bash
# Run a specific test class
pytest tests/test_safety.py::TestSafetyManager

# Run a specific test method
pytest tests/test_tool_executor.py::TestToolExecutor::test_read_file_success
```

### Run Tests by Marker

```bash
# Run only unit tests
pytest -m unit

# Run only integration tests
pytest -m integration

# Skip slow tests
pytest -m "not slow"
```

## Test Categories

### Unit Tests (NEW)

These tests use mocking and don't require external services:

- **test_tool_executor.py**: Tests file operations (read, write, edit), directory operations, file search, and bash command execution (mocked)
- **test_safety.py**: Tests dangerous command detection, safety validation, and user confirmation flows (mocked)
- **test_completion_detector.py**: Tests agent loop completion detection logic
- **test_triton_client_unit.py**: Tests Triton client with fully mocked HTTP connections

### Integration Tests (Existing)

These are the original test scripts that can be run manually:

- **test_config.py**: Tests configuration management and conversation persistence
- **test_tool_calling.py**: Tests tool call parsing from LLM responses

## Key Testing Features

### 1. No External Dependencies

All unit tests use mocking to avoid requiring:

- Running Triton server
- Network access
- External APIs
- Specific file system state

### 2. Temporary File System

Tests that need file operations use pytest's `tmp_path` fixture or our custom `temp_workspace` fixture to create isolated temporary directories.

### 3. Mocked HTTP Connections

The Triton client tests mock HTTP connections to simulate:

- Successful streaming responses
- Error responses
- Network failures
- UTF-8 encoding edge cases

### 4. Parametrized Tests

Many tests use pytest's parametrization to test multiple scenarios efficiently.

## Coverage Goals

We aim for:

- **>90% coverage** for critical business logic (tools, safety, agent loop)
- **>80% coverage** for infrastructure code (clients, config)
- **>70% coverage** overall

Check current coverage:

```bash
pytest --cov=kubrick_cli --cov-report=html
# Open htmlcov/index.html in browser
```

## CI/CD Integration

Tests run automatically in GitHub Actions on:

- Push to main, staging, or develop branches
- Pull requests to these branches

The CI pipeline:

1. Tests on multiple OS: Ubuntu, macOS, Windows
2. Tests on multiple Python versions: 3.8, 3.9, 3.10, 3.11, 3.12
3. Runs linting (flake8) and formatting checks (black)
4. Generates coverage reports
5. Uploads coverage to Codecov (optional)

## Writing New Tests

### Test Structure

```python
"""Module docstring describing what's being tested."""

import pytest
from unittest.mock import Mock, patch

from kubrick_cli.your_module import YourClass


class TestYourClass:
    """Test suite for YourClass."""

    @pytest.fixture
    def instance(self):
        """Create a YourClass instance for testing."""
        return YourClass()

    def test_basic_functionality(self, instance):
        """Test basic functionality."""
        result = instance.method()
        assert result == expected_value

    @patch('module.external_dependency')
    def test_with_mocking(self, mock_dep, instance):
        """Test with mocked external dependency."""
        mock_dep.return_value = "mocked value"
        result = instance.method_using_dependency()
        assert result is not None
        mock_dep.assert_called_once()
```

### Best Practices

1. **Use descriptive test names**: Test names should clearly describe what they test
2. **One assertion per test**: Each test should verify one specific behavior
3. **Use fixtures**: Share common setup code using pytest fixtures
4. **Mock external dependencies**: Never rely on external services in unit tests
5. **Test edge cases**: Include tests for error conditions, empty inputs, boundary values
6. **Keep tests isolated**: Tests should not depend on each other or shared state

### Testing Commands with Triton

When testing code that uses the Triton client:

```python
from unittest.mock import patch

@patch('kubrick_cli.triton_client.TritonLLMClient')
def test_with_triton_mock(mock_client):
    """Test code that uses Triton without running Triton."""
    # Configure the mock
    mock_instance = Mock()
    mock_instance.generate.return_value = "Mocked response"
    mock_client.return_value = mock_instance

    # Run your code
    result = function_that_uses_triton()

    # Verify
    assert result == expected_output
```

## Debugging Failed Tests

### Verbose Output

```bash
# Show full output including print statements
pytest -v -s

# Show full tracebacks
pytest --tb=long
```

### Run Specific Failed Test

```bash
# Re-run only failed tests from last run
pytest --lf

# Run failed tests first, then others
pytest --ff
```

### Drop into Debugger on Failure

```bash
# Start pdb on test failure
pytest --pdb

# Start pdb on test failure, but also show stdout
pytest --pdb -s
```

## Continuous Integration

### GitHub Actions Workflow

The `.github/workflows/test.yml` file defines our CI pipeline:

- **Matrix Testing**: Tests run on multiple OS and Python versions
- **Caching**: pip packages are cached for faster builds
- **Code Quality**: Runs flake8 and black checks
- **Coverage**: Generates and uploads coverage reports

### Local CI Simulation

To simulate CI locally:

```bash
# Run the same checks as CI
flake8 kubrick_cli --count --select=E9,F63,F7,F82 --show-source --statistics
black --check kubrick_cli tests
pytest tests/ -v --cov=kubrick_cli --cov-report=term-missing
```

## Troubleshooting

### Import Errors

If you get import errors when running tests:

```bash
# Make sure package is installed in editable mode
pip install -e .

# Or with dev dependencies
pip install -e ".[dev]"
```

### Missing Dependencies

```bash
# Install/upgrade all dev dependencies
pip install --upgrade -e ".[dev]"
```

### Tests Pass Locally but Fail in CI

- Check Python version (CI tests multiple versions)
- Check OS-specific behavior (CI tests Linux, macOS, Windows)
- Ensure no reliance on local file system state
- Check for hardcoded paths (use Path objects and tmp_path fixture)

## Future Test Additions

Consider adding tests for:

- [ ] Provider factory and adapter pattern
- [ ] Display manager formatting
- [ ] Progress tracking
- [ ] Conversation management
- [ ] Tool scheduling and parallel execution
- [ ] Main CLI entry point (with mocked inputs)

## Resources

- [pytest documentation](https://docs.pytest.org/)
- [pytest-mock documentation](https://pytest-mock.readthedocs.io/)
- [Coverage.py documentation](https://coverage.readthedocs.io/)
