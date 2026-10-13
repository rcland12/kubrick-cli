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

2. **Create the dev environment**

```bash
make dev    # creates .venv (with uv) and installs Kubrick editable with all extras
```

Everything stays inside the repo: `.venv/` for packages and `.dev/` for the dev run's
config, keys, history, and playground project. `make reset` deletes both. Without `make`
or `uv`: `python -m venv .venv && .venv/bin/pip install -e ".[dev,all]"`.

3. **Try your changes**

```bash
make run                         # throwaway playground copy of examples/playground
make run DIR=~/src/some-project  # a real project
make run ARGS="-p 'hi'"          # pass flags
make sandbox                     # same, inside Docker
```

`make run` uses `.dev/home` instead of `~/.kubrick`, so the setup wizard runs the first
time; `make reset-home` brings it back. Commands the agent runs inherit the venv, so a
`pip install` lands in `.venv`, not your system. For full isolation, `make sandbox` runs
Kubrick in a container that can only see the project directory (Kubrick's source is
mounted read-only, so edits apply without a rebuild). `make playground` restores the
playground's original bugs.

4. **Install pre-commit hooks** (recommended)

```bash
pip install pre-commit
pre-commit install
```

This will run automated checks before each commit.

## Development Workflow

### Branch Strategy

- `master`: Production-ready code, protected branch. A merge that changes `version` in
  `pyproject.toml` releases to PyPI, Docker Hub, and GHCR
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

Once your feature is merged to `staging`, it's published to Test PyPI if its version isn't
there yet (uploads use `skip-existing`, so bump the version first). Validate it in a
throwaway environment:

```bash
uv venv /tmp/kubrick-rc
uv pip install --python /tmp/kubrick-rc/bin/python --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ kubrick-cli==X.Y.Z
/tmp/kubrick-rc/bin/kubrick --version
```

This ensures the package works correctly before releasing to production PyPI.

## Code Standards

### Style Guidelines

- Follow PEP 8 style guide
- Black formats the code (default 88 columns); flake8 allows up to 100
- Use type hints, in Python 3.9-compatible syntax (`Optional[X]`, not `X | None`)

### Pre-commit Checks

The project uses pre-commit hooks that run automatically:

- **Black**: Code formatting
- **Flake8**: Style checking
- **Bandit**: Security scanning
- File validators (trailing whitespace, etc.)

### Manual Formatting

```bash
make fmt                          # black
make lint                         # black --check + flake8, as CI runs them
bandit -r kubrick_cli -ll         # security check (also in CI)
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

3. **Merge to master** by opening a pull request from `staging` to `master` (master is
   protected)

**That's it!** The CD workflow automatically:

- Detects the version change
- Runs tests
- Publishes to PyPI
- Builds and pushes multi-arch Docker images to Docker Hub and GHCR
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
├── docker/                 # Dev sandbox image (make sandbox)
├── docs/                   # Documentation
├── examples/               # Playground project, Triton model example
├── kubrick_cli/            # Main package
│   ├── providers/          # LLM provider adapters
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   └── ...
├── scripts/                # Helper scripts
├── tests/                  # Test files
├── Makefile                # Dev tasks: make dev/run/test/lint/sandbox/reset
├── pyproject.toml          # Project configuration
├── Dockerfile              # Release image
├── docker-compose.yaml
└── README.md
```

## Getting Help

- **Questions**: Create a [Discussion](https://github.com/rcland12/kubrick-cli/discussions)
- **Bugs**: Create an [Issue](https://github.com/rcland12/kubrick-cli/issues)
- **Security**: Email security concerns to rcland12@gmail.com

## Recognition

Contributors will be recognized in:

- Release notes
- GitHub contributors page

Thank you for contributing to Kubrick CLI! 🎉
