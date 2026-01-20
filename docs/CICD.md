# CI/CD Pipeline Documentation

This document describes the CI/CD pipeline for kubrick-cli, including setup instructions and usage.

## Table of Contents

- [Overview](#overview)
- [Workflows](#workflows)
- [Setup Instructions](#setup-instructions)
- [Making a Release](#making-a-release)
- [Additional Recommendations](#additional-recommendations)

## Overview

The kubrick-cli project uses GitHub Actions for automated testing, building, and deployment. The pipeline includes:

- **Continuous Integration (CI)**: Runs on all branches/PRs
  - Code linting and formatting checks
  - Security scanning
  - Unit tests across multiple Python versions
  - Package build verification

- **Continuous Deployment (CD)**: Runs only on version tag pushes
  - Automated versioning
  - PyPI package publishing
  - Docker image building and pushing
  - GitHub release creation with artifacts

## Workflows

### CI Workflow (`.github/workflows/ci.yml`)

**Triggers:**
- Push to any branch
- Pull request to any branch

**Jobs:**

1. **Lint** - Code quality checks
   - Black (code formatter)
   - Flake8 (style checker)
   - Bandit (security scanner)

2. **Test** - Run tests
   - Tests on Python 3.9, 3.10, 3.11, 3.12
   - Code coverage reporting
   - Upload coverage to Codecov

3. **Build** - Package verification
   - Build wheel and source distribution
   - Verify package integrity with twine

### CD Workflow (`.github/workflows/cd.yml`)

**Triggers:**
- Push of version tags (format: `v*.*.*`, e.g., `v0.1.2`)

**Jobs:**

1. **Test** - Final pre-release testing
   - Run full test suite

2. **Publish to PyPI**
   - Extract version from git tag
   - Update `pyproject.toml` version
   - Build package
   - Publish to PyPI using trusted publishing

3. **Publish Docker Image**
   - Build multi-platform images (amd64, arm64)
   - Tag with version and `latest`
   - Push to Docker Hub

4. **Create GitHub Release**
   - Generate changelog from commits
   - Create release with notes
   - Attach wheel and source distribution

## Setup Instructions

### Prerequisites

1. GitHub repository at `rcland12/kubrick-cli`
2. PyPI account
3. Docker Hub account

### 1. Configure PyPI Publishing

#### Option A: Trusted Publishing (Recommended)

This is the most secure method and doesn't require API tokens.

1. Go to [PyPI Account Settings](https://pypi.org/manage/account/)
2. Scroll to "Publishing" section
3. Click "Add a new pending publisher"
4. Fill in:
   - **PyPI Project Name**: `kubrick-cli`
   - **Owner**: `rcland12`
   - **Repository name**: `kubrick-cli`
   - **Workflow name**: `cd.yml`
   - **Environment name**: (leave blank)

5. Click "Add"

**Note**: The first time you publish, you'll need to create the PyPI project. After initial setup, trusted publishing will work automatically.

#### Option B: API Token (Alternative)

If you prefer using an API token:

1. Go to [PyPI Account Settings](https://pypi.org/manage/account/)
2. Scroll to "API tokens"
3. Click "Add API token"
4. Name: `kubrick-cli-github-actions`
5. Scope: "Entire account" or specific to `kubrick-cli` project
6. Copy the token (starts with `pypi-`)

7. Add to GitHub Secrets:
   - Go to your repository → Settings → Secrets and variables → Actions
   - Click "New repository secret"
   - Name: `PYPI_API_TOKEN`
   - Value: (paste the token)

### 2. Configure Docker Hub

1. Log in to [Docker Hub](https://hub.docker.com/)
2. Go to Account Settings → Security → Access Tokens
3. Click "New Access Token"
4. Description: `kubrick-cli-github-actions`
5. Permissions: "Read & Write"
6. Copy the token

7. Add secrets to GitHub:
   - Go to your repository → Settings → Secrets and variables → Actions
   - Add two secrets:
     - `DOCKERHUB_USERNAME`: Your Docker Hub username (e.g., `rcland12`)
     - `DOCKERHUB_TOKEN`: The access token you just created

### 3. Configure Codecov (Optional but Recommended)

1. Go to [Codecov](https://codecov.io/)
2. Sign in with GitHub
3. Add your repository
4. Get the upload token
5. Add to GitHub Secrets:
   - Name: `CODECOV_TOKEN`
   - Value: (paste the token)

**Note**: If you skip this, coverage reports won't be uploaded, but CI will still work.

### 4. Enable GitHub Actions

1. Go to your repository → Settings → Actions → General
2. Under "Actions permissions", select "Allow all actions and reusable workflows"
3. Under "Workflow permissions", select "Read and write permissions"
4. Check "Allow GitHub Actions to create and approve pull requests"
5. Click "Save"

### 5. Protect Master Branch (Recommended)

1. Go to Settings → Branches
2. Click "Add branch protection rule"
3. Branch name pattern: `master`
4. Enable:
   - ✅ Require a pull request before merging
   - ✅ Require status checks to pass before merging
   - Select: `Lint Code`, `Test on Python 3.11`, `Build Package`
   - ✅ Require branches to be up to date before merging
5. Click "Create"

## Making a Release

### Method 1: Using the Release Script (Recommended)

The release script automates version bumping and tagging:

```bash
# Make sure you're on master and everything is committed
git checkout master
git pull origin master

# Run the release script
./scripts/release.sh [patch|minor|major]
```

**Examples:**

```bash
# Patch release (0.1.1 → 0.1.2)
./scripts/release.sh patch

# Minor release (0.1.2 → 0.2.0)
./scripts/release.sh minor

# Major release (0.2.0 → 1.0.0)
./scripts/release.sh major
```

The script will:
1. ✅ Check you're on master branch
2. ✅ Check working directory is clean
3. ✅ Bump version in `pyproject.toml`
4. ✅ Commit the version change
5. ✅ Create and push a git tag
6. ✅ Trigger the CD pipeline

### Method 2: Manual Release

If you prefer to do it manually:

```bash
# 1. Update version in pyproject.toml
vim pyproject.toml
# Change: version = "0.1.2"

# 2. Commit the change
git add pyproject.toml
git commit -m "chore: bump version to 0.1.2"

# 3. Create a tag
git tag -a v0.1.2 -m "Release v0.1.2"

# 4. Push everything
git push origin master
git push origin v0.1.2
```

### What Happens After Release

Once you push a version tag, the CD workflow automatically:

1. **Runs Tests** - Ensures everything passes
2. **Publishes to PyPI** - Available via `pip install kubrick-cli==0.1.2`
3. **Builds Docker Image** - Available via `docker pull rcland12/kubrick-cli:0.1.2`
4. **Creates GitHub Release** - Includes changelog and downloadable artifacts

**Monitor Progress:**
- Go to: https://github.com/rcland12/kubrick-cli/actions
- Watch the "CD - Release" workflow

**Release Locations:**
- 📦 PyPI: https://pypi.org/project/kubrick-cli/
- 🐳 Docker Hub: https://hub.docker.com/r/rcland12/kubrick-cli
- 🎉 GitHub: https://github.com/rcland12/kubrick-cli/releases

## Development Workflow

### Daily Development

```bash
# Work on staging branch
git checkout staging
git pull origin staging

# Make changes
git add .
git commit -m "feat: add new feature"
git push origin staging

# CI runs automatically - checks pass ✅
```

### Merging to Master

```bash
# Create PR from staging to master
# Review and merge on GitHub

# CI runs on master - checks pass ✅
# No deployment yet (only happens on tags)
```

### Releasing

```bash
# On master, create a release
git checkout master
git pull origin master

# Use release script
./scripts/release.sh patch

# CD workflow triggers automatically 🚀
# - Tests pass ✅
# - PyPI published ✅
# - Docker image built ✅
# - GitHub release created ✅
```

## Additional Recommendations

### 1. Add Dependabot

Keep dependencies up to date automatically.

Create `.github/dependabot.yml`:

```yaml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 5

  - package-ecosystem: "docker"
    directory: "/"
    schedule:
      interval: "weekly"

  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
```

### 2. Add Pre-commit Hooks

Catch issues before committing.

Create `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/psf/black
    rev: 23.3.0
    hooks:
      - id: black

  - repo: https://github.com/pycqa/flake8
    rev: 6.0.0
    hooks:
      - id: flake8
        args: ['--max-line-length=100', '--extend-ignore=E203,W503']

  - repo: https://github.com/PyCQA/bandit
    rev: 1.7.5
    hooks:
      - id: bandit
        args: ['-ll']

  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.4.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
```

Install: `pip install pre-commit && pre-commit install`

### 3. Add Security Scanning

Create `.github/workflows/security.yml`:

```yaml
name: Security Scan

on:
  schedule:
    - cron: '0 0 * * 0'  # Weekly
  workflow_dispatch:

jobs:
  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: snyk/actions/python@master
        env:
          SNYK_TOKEN: ${{ secrets.SNYK_TOKEN }}
```

### 4. Add Documentation Building

If you add Sphinx docs later:

```yaml
name: Documentation

on:
  push:
    branches: [master]

jobs:
  docs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: |
          pip install sphinx sphinx-rtd-theme
          cd docs && make html
      - uses: peaceiris/actions-gh-pages@v3
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: ./docs/_build/html
```

### 5. Add Performance Testing

Monitor performance regressions:

```yaml
name: Performance Tests

on:
  pull_request:
    branches: [master, staging]

jobs:
  perf:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
      - run: |
          pip install pytest pytest-benchmark
          pytest tests/perf/ --benchmark-only
```

### 6. Add Release Notifications

Notify your team on releases:

```yaml
# Add to cd.yml at the end
      - name: Send Slack Notification
        uses: slackapi/slack-github-action@v1
        with:
          payload: |
            {
              "text": "🚀 New release: kubrick-cli v${{ steps.get_version.outputs.VERSION }}"
            }
        env:
          SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK }}
```

### 7. Add Docker Image Scanning

Scan Docker images for vulnerabilities:

```yaml
# Add to cd.yml after docker build
      - name: Scan Docker image
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: rcland12/kubrick-cli:${{ steps.get_version.outputs.VERSION }}
          format: 'sarif'
          output: 'trivy-results.sarif'

      - name: Upload scan results
        uses: github/codeql-action/upload-sarif@v2
        with:
          sarif_file: 'trivy-results.sarif'
```

## Troubleshooting

### PyPI Publishing Fails

**Error**: "File already exists"
- **Cause**: Version already published
- **Solution**: Bump version number and try again

**Error**: "Invalid credentials"
- **Cause**: PYPI_API_TOKEN not set or invalid
- **Solution**: Regenerate token and update secret

### Docker Push Fails

**Error**: "Authentication required"
- **Cause**: DOCKERHUB_TOKEN not set
- **Solution**: Create access token and add to secrets

**Error**: "Tag already exists"
- **Cause**: Image with same tag already pushed
- **Solution**: This shouldn't happen with proper versioning. Delete tag if needed.

### Tests Fail on CI but Pass Locally

- Check Python version (CI uses multiple versions)
- Check dependencies are pinned correctly
- Look at CI logs for specific errors
- Try running in fresh virtualenv

### Release Not Triggering

- Verify tag format is `v*.*.*` (e.g., `v0.1.2`)
- Check if CD workflow is enabled
- Check GitHub Actions settings
- Look at Actions tab for errors

## Support

For issues with the CI/CD pipeline:
1. Check the [Actions](https://github.com/rcland12/kubrick-cli/actions) tab
2. Review workflow logs for errors
3. Create an issue with relevant logs
4. Tag with `ci/cd` label
