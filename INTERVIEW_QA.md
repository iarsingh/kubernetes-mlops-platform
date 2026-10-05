# kubernetes-mlops-platform — interview questions and answers

[README](README.md) · [Project architecture](PROJECT_ARCHITECTURE.md)

Answers below use this repository’s files and implementation. They distinguish existing behavior from suggested extensions; source links let you verify each walkthrough.

## 1. What problem does kubernetes-mlops-platform address, and what can you demonstrate?

An end-to-end MLOps reference with MLflow, FastAPI, Docker, Kubernetes, Helm, Prometheus, Grafana, and GitHub Actions.

I would demonstrate the linked implementation or examples and distinguish that evidence from any planned production features. Start with [`README.md`](README.md).

## 2. How is this repository organized?

- [`src/inference/main.py`](src/inference/main.py): Implementation or supporting configuration.
- [`src/common/dataset.py`](src/common/dataset.py): Implementation or supporting configuration.
- [`src/training/evaluate.py`](src/training/evaluate.py): Implementation or supporting configuration.
- [`src/inference/model_loader.py`](src/inference/model_loader.py): Implementation or supporting configuration.
- [`src/training/train.py`](src/training/train.py): Implementation or supporting configuration.
- [`requirements.txt`](requirements.txt): Implementation or supporting configuration.
- [`terraform/main.tf`](terraform/main.tf): Terraform resource/module declarations.
- [`terraform/modules/artifact-registry/main.tf`](terraform/modules/artifact-registry/main.tf): Terraform resource/module declarations.

[PROJECT_ARCHITECTURE.md](PROJECT_ARCHITECTURE.md) contains the component diagram and the implementation walkthrough.

## 3. Can you walk through `generate_dataset` and explain the decision it makes?

The main walkthrough here is `generate_dataset(n_samples: int=8000, seed: int=42)` in [`src/common/dataset.py`](src/common/dataset.py#L22). Generate a reproducible synthetic churn dataset.

Parameters
----------
n_samples:
    Number of rows to generate.
seed:
    RNG seed for reproducibility.

Returns
-------
pandas.DataFrame
    A frame with :data:`FEATURE_NAMES` columns plus the binary
    :data:`TARGET_NAME` column.

```python
def generate_dataset(n_samples: int = 8_000, seed: int = 42) -> pd.DataFrame:
    """Generate a reproducible synthetic churn dataset.

    Parameters
    ----------
    n_samples:
        Number of rows to generate.
    seed:
        RNG seed for reproducibility.

    Returns
    -------
    pandas.DataFrame
        A frame with :data:`FEATURE_NAMES` columns plus the binary
        :data:`TARGET_NAME` column.
    """
    rng = np.random.default_rng(seed)

    account_age_months = rng.gamma(shape=2.0, scale=12.0, size=n_samples).clip(0, 240)
    monthly_charges = rng.normal(70, 25, size=n_samples).clip(5, 500)
```

This is an excerpt; follow the source link for the rest of the branches.

The implementation calls `_z`, `churned.astype`, `np.exp`, `np.random.default_rng`, `num_logins_last_30d.astype`, `num_support_tickets.astype`, `pd.DataFrame`, `rng.binomial`, `rng.binomial(1, 0.35, size=n_samples).astype`. In an interview, trace those calls in execution order using a fixture input.

## 4. What responsibility does `gate_and_promote` have?

`gate_and_promote(client: MlflowClient, version: str, metrics: dict, args: argparse.Namespace)` is defined in [`src/training/evaluate.py`](src/training/evaluate.py#L95). Promote to the production alias iff metrics clear the thresholds.

Its return expressions include:

- `passed`

It uses `client.set_model_version_tag`, `client.set_registered_model_alias`, `logger.info`, `logger.warning`. This is the code path I would compare against the caller to explain responsibility boundaries.

## 5. What input validation and failure behavior are implemented?

Explicit failure paths include:

- `HTTPException(status_code=422, detail=f'instance {i} missing features: {missing}')` in [`src/inference/main.py`](src/inference/main.py#L126).
- `HTTPException(status_code=503, detail=str(exc))` in [`src/inference/main.py`](src/inference/main.py#L228).
- `HTTPException(status_code=500, detail=f'inference error: {exc}')` in [`src/inference/main.py`](src/inference/main.py#L265).
- `HTTPException(status_code=422, detail=f"instance {i} feature '{f}'={val} out of range [{spec.minimum}, {spec.maximum}]")` in [`src/inference/main.py`](src/inference/main.py#L141).
- `HTTPException(status_code=503, detail=f'model unavailable: {exc}')` in [`src/inference/main.py`](src/inference/main.py#L250).
- `HTTPException(status_code=422, detail=f"instance {i} feature '{f}' is not numeric")` in [`src/inference/main.py`](src/inference/main.py#L135).
- `ModelLoadError(f"No local model at '{path}'. Run training with MLFLOW_TRACKING_URI unset to populate ./mlruns, or export a model to LOCAL_MODEL_PATH.")` in [`src/inference/model_loader.py`](src/inference/model_loader.py#L87).

I would test both the condition that reaches each exception and the caller that translates it. An explicit raise does not mean every malformed input or dependency failure is handled.

## 6. Which test would you use to demonstrate correctness?

The tests include [`tests/conftest.py`](tests/conftest.py). I would trace their setup and assertions before selecting an acceptance example.

## 7. What HTTP interface does the code expose?

- `GET /` → `root` in [`src/inference/main.py`](src/inference/main.py#L182).
- `GET /health` → `health` in [`src/inference/main.py`](src/inference/main.py#L195).
- `GET /ready` → `ready` in [`src/inference/main.py`](src/inference/main.py#L201).
- `GET /metrics` → `metrics` in [`src/inference/main.py`](src/inference/main.py#L215).
- `POST /reload` → `reload_model` in [`src/inference/main.py`](src/inference/main.py#L221).
- `POST /predict` → `predict` in [`src/inference/main.py`](src/inference/main.py#L239).

These are literal decorators. Application/router prefixes, authentication, and middleware must be checked in the corresponding setup code.

## 8. Where does state live, and what happens with multiple workers?

Module-level containers include `FEATURE_NAMES`, `CLASS_LABELS`, `FEATURE_SPECS` in [`src/common/schema.py`](src/common/schema.py).

These containers belong to a Python process. Inspect which are constant fixtures and which are mutated. Mutable process state needs an explicit shared-storage or synchronization strategy before multiple workers can provide consistent behavior.

## 9. How would another engineer reproduce your walkthrough?

Start from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -q
```

These commands follow repository manifests; environment setup and command results still need to be checked on the target machine.

## 10. What does automation verify, and what does it not prove?

Inspect [`.github/workflows/ci.yml`](.github/workflows/ci.yml), [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml), [`.github/workflows/docker-build.yml`](.github/workflows/docker-build.yml) for triggers, permissions, and job commands. I would name the checks that those definitions run and show the latest run separately. A workflow definition alone does not establish a successful deployment, security review, or production SLO.

## 11. How would you present this project in a Forward Deployed Engineer interview?

Start with the user and operational problem described in [`README.md`](README.md). Explain one constraint that changes the implementation, show the linked code or example, and walk through a success case and a failure case. Agree on a measurable acceptance criterion before expanding the solution, and leave a handoff with data boundaries and rollback ownership. Any proposed production or business metric should be identified as a target until measured.

## 12. What is the input-to-output contract of `generate_dataset`?

In [`src/common/dataset.py`](src/common/dataset.py#L22), `generate_dataset(n_samples: int=8000, seed: int=42)` receives the inputs. The function computes these intermediate values:

- `rng = np.random.default_rng(seed)`
- `account_age_months = rng.gamma(shape=2.0, scale=12.0, size=n_samples).clip(0, 240)`
- `monthly_charges = rng.normal(70, 25, size=n_samples).clip(5, 500)`
- `total_charges = monthly_charges * account_age_months * rng.uniform(0.8, 1.2, size=n_samples)`
- `num_support_tickets = rng.poisson(1.5, size=n_samples).clip(0, 100)`
- `avg_latency_ms = rng.normal(180, 90, size=n_samples).clip(1, 5000)`
- `data_usage_gb = rng.gamma(shape=2.0, scale=40.0, size=n_samples).clip(0, 10000)`

Its result is defined by:

- `frame`

## 13. Which Terraform modules compose the environment?

- `module.artifact_registry` uses `./modules/artifact-registry` in [`terraform/main.tf`](terraform/main.tf).
- `module.mlflow_artifacts` uses `./modules/gcs-bucket` in [`terraform/main.tf`](terraform/main.tf).

Review each module’s variable and output contracts. Different environment declarations may reuse a module with different inputs; state and provider configuration determine the actual deployment boundary.
