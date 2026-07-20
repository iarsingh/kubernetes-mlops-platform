# Contributing

Thanks for your interest in improving this project. This guide covers local
setup, testing, and PR conventions.

## Local setup

Prerequisites: Python 3.12+, Docker, and (for the K8s bits) `helm`, `kubectl`,
and `terraform`.

```bash
# 1. Create a virtualenv and install dependencies
make venv
source .venv/bin/activate

# 2. Run the full local stack (Postgres + MinIO + MLflow + API)
make compose-up

# 3. Train + register a model against the local MLflow, then promote it
make train    MLFLOW_TRACKING_URI=http://localhost:5000
make evaluate MLFLOW_TRACKING_URI=http://localhost:5000

# 4. Hit the API
curl localhost:8000/health
curl localhost:8000/ready
```

To iterate on the API without the full stack, use the SQLite backend:

```bash
make train MLFLOW_TRACKING_URI=sqlite:///mlflow.db
make serve   # uvicorn with --reload
```

## Running checks

Everything CI runs, you can run locally:

```bash
make lint          # ruff check + format --check
make test          # pytest with coverage
make helm-lint     # helm lint
make helm-template # render the chart
make tf-validate   # terraform fmt + validate
```

Please make sure `make lint` and `make test` pass before opening a PR. Add or
update tests for any behavior change — the suite includes unit tests for the
training/dataset logic, API tests via FastAPI's `TestClient`, and a test that
mocks the MLflow client.

## Branch & PR conventions

- Branch off `main`: `feat/<short-name>`, `fix/<short-name>`, `docs/<short-name>`,
  or `chore/<short-name>`.
- Commit messages follow **Conventional Commits**
  (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`).
- Keep PRs focused and small where possible; include a clear description of what
  changed and why.
- CI must be green (lint, tests, helm lint, terraform validate, image scan).
- For infra changes, paste relevant `terraform plan` / `helm template` diffs in
  the PR description.

## Code style

- Python formatted and linted with **ruff** (config defaults; line length 88).
- Type hints are encouraged; prefer small, testable pure functions.
- Keep the feature contract in `src/common/schema.py` as the single source of
  truth — do not hardcode feature lists elsewhere.
