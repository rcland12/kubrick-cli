# CI/CD

Four GitHub Actions workflows live in `.github/workflows/`. Releases are driven by the
`version` in `pyproject.toml`: there is no release script and tags are created by CI.

## Workflows

| Workflow | Runs on | What it does |
|---|---|---|
| `ci.yml` | every push and PR, all branches | lint, tests, package build; TestPyPI on `staging` |
| `cd.yml` | pushes to `master` | releases if the push changed `version` |
| `security.yml` | pushes, PRs, weekly | CodeQL, Bandit, Semgrep, dependency check, Trivy image scan |
| `scorecard.yml` | pushes to `master`, weekly | OSSF Scorecard (kept separate: it rejects workflows with write permissions at the top level or container jobs) |

### CI (`ci.yml`)

1. **Lint** (blocking): `black --check .`, `flake8 kubrick_cli tests
   --max-line-length=100 --extend-ignore=E203,W503`, `bandit -r kubrick_cli -ll`.
2. **Test**: `pytest` with coverage on Python 3.9, 3.10, 3.11, 3.12, 3.13 (Ubuntu).
   Coverage is uploaded to Codecov from 3.11 (non-blocking, no token needed).
3. **Build**: `python -m build` + `twine check`, artifacts kept for 7 days.
4. **Publish to TestPyPI**: only on pushes to `staging`, using `TEST_PYPI_API_TOKEN`, with
   `skip-existing`: a version already on TestPyPI is not re-uploaded, so bump the version
   before relying on it.

Run the same checks locally with `make lint` and `make test` (bandit:
`bandit -r kubrick_cli -ll`).

### CD (`cd.yml`)

On every push to `master`, `check-version` compares `pyproject.toml` with the previous
commit. If `version` didn't change, nothing else runs. If it did:

1. Tests run again (Python 3.11).
2. **PyPI**: build and publish with `PYPI_API_TOKEN`.
3. **Docker**: multi-arch (`linux/amd64`, `linux/arm64`) images pushed to Docker Hub
   (`rcland12/kubrick-cli`, needs `DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN`) and GHCR
   (`ghcr.io/rcland12/kubrick-cli`, uses `GITHUB_TOKEN`), tagged `X.Y.Z`, `X.Y`, `X`, and
   `latest`, then scanned with Trivy (non-blocking).
4. **Tag and release**: creates tag `vX.Y.Z` and a GitHub Release with the commit log and the
   wheel/sdist attached.

PyPI and Docker publish in parallel after the tests. The GitHub Release only happens if
both succeed.

## Secrets

| Secret | Used by |
|---|---|
| `PYPI_API_TOKEN` | `cd.yml` (PyPI) |
| `TEST_PYPI_API_TOKEN` | `ci.yml` (TestPyPI, `staging` only) |
| `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN` | `cd.yml` (Docker Hub) |
| `SEMGREP_APP_TOKEN` | `security.yml` (optional) |

`GITHUB_TOKEN` is provided automatically.

## Releasing

1. On a feature branch, bump `version` in `pyproject.toml`, update `CHANGELOG.md`, and
   open a PR into `staging`.
2. When it merges, CI publishes that version to TestPyPI. Try it in a clean environment:

   ```bash
   uv venv /tmp/kubrick-rc && uv pip install --python /tmp/kubrick-rc/bin/python \
     --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ \
     kubrick-cli==X.Y.Z
   /tmp/kubrick-rc/bin/kubrick --version
   ```

3. Open a PR from `staging` to `master` and merge it. CD publishes to PyPI, Docker Hub,
   and GHCR, then tags and creates the GitHub Release.
4. Users get it with `kubrick update`.

Merging to `master` without a version change runs CI only and releases nothing.

## Troubleshooting

- **Nothing was released:** the push to `master` didn't change the `version` line. Check
  the `check-version` job's log.
- **PyPI upload rejected:** that version already exists on PyPI (versions can't be
  reused), or `PYPI_API_TOKEN` is expired or scoped to another project.
- **TestPyPI didn't get the new build:** `skip-existing` skipped it because the version was
  already uploaded; bump the version.
- **Docker push fails:** check `DOCKERHUB_TOKEN` hasn't expired and has write access.
- **Passes locally, fails in CI:** run the oldest and newest Pythons locally, e.g.
  `uv venv --python 3.9 /tmp/k39 && uv pip install --python /tmp/k39/bin/python -e ".[dev]"`
  then `/tmp/k39/bin/pytest`.
