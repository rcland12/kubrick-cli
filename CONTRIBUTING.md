# Contributing to Kubrick CLI

Thank you for considering contributing to Kubrick CLI! This document provides guidelines and instructions for contributing.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Workflow](#development-workflow)
- [Code Standards](#code-standards)
- [Testing](#testing)
- [Submitting Changes](#submitting-changes)
- [Release Process](#release-process)

## Code of Conduct

This project follows the standard open source code of conduct:

- Be respectful and inclusive
- Welcome newcomers
- Focus on constructive feedback
- Maintain a professional and collaborative environment

## Getting Started

### Prerequisites

- Python 3.9 or higher
- Git
- Docker (optional, for testing Docker functionality)

### Setup Development Environment

1. **Fork and clone the repository**

```bash
git clone https://github.com/rcland12/kubrick-cli.git
cd kubrick-cli
```

2. **Create a virtual environment**

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. **Install in development mode**

```bash
pip install -e ".[dev]"
```

4. **Install pre-commit hooks** (recommended)

```bash
pip install pre-commit
pre-commit install
```

This will run automated checks before each commit.

## Development Workflow

### Branch Strategy

- `master`: Production-ready code, protected branch, triggers PyPI and Docker Hub releases
- `staging`: Main development branch, automatically publishes to Test PyPI for validation
- `feature/*`: Feature branches (branched from staging)
- `bugfix/*`: Bug fix branches (branched from staging)
- `hotfix/*`: Urgent fixes (branched from master)

### Creating a Feature

1. **Create a feature branch from staging**

```bash
git checkout staging
git pull origin staging
git checkout -b feature/your-feature-name
```

2. **Make your changes**

Write code, add tests, update documentation.

3. **Commit your changes**

```bash
git add .
git commit -m "feat: add your feature description"
```

Use conventional commits:

- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation changes
- `style:` - Code style changes (formatting, etc.)
- `refactor:` - Code refactoring
- `test:` - Adding or updating tests
- `chore:` - Maintenance tasks

4. **Push and create a Pull Request**

```bash
git push origin feature/your-feature-name
```

Then create a PR from your branch to `staging`.

5. **Validate from Test PyPI** (after merging to staging)

Once your feature is merged to `staging`, it's automatically published to Test PyPI. You can validate it works:

```bash
# Install from Test PyPI
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ kubrick-cli

# Test your changes
kubrick --version
kubrick --help
```

This ensures the package works correctly before releasing to production PyPI.

## Code Standards

### Style Guidelines

- Follow PEP 8 style guide
- Use Black for code formatting
- Maximum line length: 100 characters
- Use type hints where appropriate

### Pre-commit Checks

The project uses pre-commit hooks that run automatically:

- **Black**: Code formatting
- **Flake8**: Style checking
- **Bandit**: Security scanning
- **MyPy**: Type checking
- File validators (trailing whitespace, etc.)

### Manual Formatting

```bash
# Format code
black .

# Check style
flake8 kubrick_cli --max-line-length=100 --extend-ignore=E203,W503

# Security check
bandit -r kubrick_cli -ll
```

## Testing

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=kubrick_cli --cov-report=term

# Run specific test file
pytest tests/test_config.py

# Run with verbose output
pytest -v
```

### Writing Tests

- Place tests in the `tests/` directory
- Name test files `test_*.py`
- Name test functions `test_*`
- Use descriptive test names
- Include both positive and negative test cases
- Mock external dependencies

Example:

```python
def test_config_initialization():
    """Test that config initializes with correct defaults."""
    config = KubrickConfig(skip_wizard=True)
    assert config.kubrick_dir.exists()
    assert config.config_file.name == "config.json"
```

### Test Coverage

Aim for >80% code coverage. The CI pipeline tracks coverage and will report on PRs.

## Submitting Changes

### Pull Request Process

1. **Ensure all tests pass**

```bash
pytest -v
```

2. **Update documentation**

If you've added features or changed behavior, update:

- README.md
- Relevant docs in `docs/`
- Docstrings in code

3. **Create a Pull Request**

- Title: Use conventional commit format
- Description: Explain what and why
- Link related issues
- Add screenshots if relevant

4. **Code Review**

- Address review comments
- Keep discussions professional and constructive
- Make requested changes in new commits

5. **Merge**

Once approved:

- Maintainer will squash and merge to staging
- Delete your feature branch after merge

### Pull Request Template

When creating a PR, include:

```markdown
## Description

Brief description of changes

## Type of Change

- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing

- [ ] All tests pass locally
- [ ] Added tests for new features
- [ ] Updated relevant documentation

## Checklist

- [ ] Code follows style guidelines
- [ ] Self-review completed
- [ ] Comments added for complex code
- [ ] Documentation updated
- [ ] No new warnings generated
```

## Release Process

### For Maintainers Only

Releases are automated through GitHub Actions. See [docs/CICD.md](docs/CICD.md) for full details.

**Simple Release Steps:**

1. **Update version in `pyproject.toml`**

```toml
[project]
version = "0.1.2"  # Update this
```

2. **Commit the version change**

```bash
git add pyproject.toml
git commit -m "chore: bump version to 0.1.2"
```

3. **Merge to master**

```bash
git checkout master
git merge staging
git push origin master
```

**That's it!** The CD workflow automatically:

- Detects the version change
- Runs tests
- Publishes to PyPI
- Builds and pushes Docker image
- Creates git tag (v0.1.2)
- Creates GitHub release with changelog

### Version Numbering

We use [Semantic Versioning](https://semver.org/):

- **MAJOR** (1.0.0): Breaking changes
- **MINOR** (0.1.0): New features, backward compatible
- **PATCH** (0.0.1): Bug fixes, backward compatible

### Skipping Release

If you merge to master without changing the version in `pyproject.toml`, only CI runs (no deployment). This is useful for documentation updates or minor fixes that don't warrant a release.

## Project Structure

```
kubrick-cli/
├── .github/
│   ├── workflows/          # CI/CD pipelines
│   └── dependabot.yml      # Dependency updates
├── docs/                   # Documentation
├── kubrick_cli/            # Main package
│   ├── providers/          # LLM provider adapters
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   └── ...
├── scripts/                # Helper scripts
├── tests/                  # Test files
├── pyproject.toml          # Project configuration
├── Dockerfile              # Docker configuration
└── README.md
```

## Getting Help

- **Questions**: Create a [Discussion](https://github.com/rcland12/kubrick-cli/discussions)
- **Bugs**: Create an [Issue](https://github.com/rcland12/kubrick-cli/issues)
- **Security**: Email security concerns to rcland12@gmail.com

## Recognition

Contributors will be recognized in:

- README.md contributors section
- Release notes
- GitHub contributors page

Thank you for contributing to Kubrick CLI! 🎉
