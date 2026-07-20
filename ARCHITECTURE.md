# Architecture

## System overview

```mermaid
flowchart TB
    subgraph Dev["Development & CI"]
        DEV[Engineer / GitHub Actions]
        TRAIN["Training job<br/>src/training/train.py"]
        EVAL["Evaluation gate<br/>src/training/evaluate.py"]
    end

    subgraph MLflow["MLflow"]
        TRACK[(Tracking server<br/>+ Postgres metadata)]
        REG[[Model Registry<br/>churn-classifier]]
        ART[(Artifact store<br/>GCS / MinIO)]
    end

    subgraph K8s["Kubernetes (GKE)"]
        API["ml-api Deployment<br/>FastAPI + uvicorn"]
        HPA{{HorizontalPodAutoscaler}}
        SVC[Service ClusterIP]
    end

    subgraph Obs["Observability"]
        PROM[(Prometheus)]
        GRAF[Grafana dashboard]
    end

    DEV --> TRAIN
    TRAIN -->|log params/metrics/artifacts| TRACK
    TRAIN -->|register version + 'staging' alias| REG
    TRACK --- ART
    EVAL -->|load staging version| REG
    EVAL -->|promote to 'champion' if metrics pass| REG
    API -->|load models:/churn-classifier@champion| REG
    REG --- ART
    SVC --> API
    HPA -. scales .-> API
    API -->|/metrics| PROM
    PROM --> GRAF
    CLIENT[Client] -->|POST /predict| SVC
```

## Component responsibilities

| Component | Path | Responsibility |
|-----------|------|----------------|
| Dataset generator | `src/common/dataset.py` | Deterministic synthetic churn data — no external data dependency |
| Feature schema | `src/common/schema.py` | Single source of truth for feature names/ranges shared by train + serve |
| Training | `src/training/train.py` | Fit GBM pipeline, log to MLflow, register version, set `staging` alias |
| Evaluation gate | `src/training/evaluate.py` | Re-score staging version, promote to `champion` only above thresholds |
| Model loader | `src/inference/model_loader.py` | Load `champion` from registry; documented local fallback |
| Inference API | `src/inference/main.py` | FastAPI: `/predict`, `/health`, `/ready`, `/metrics`, `/reload` |
| Helm chart | `helm/ml-api/` | Deploy, HPA, PDB, probes, ServiceMonitor, RBAC-light SA |
| Terraform | `terraform/` | Artifact Registry, GCS artifact store, spot training pool, Workload Identity |
| Monitoring | `monitoring/` | Prometheus alert rules + Grafana dashboard |
| CI/CD | `.github/workflows/` | Lint/test, build+scan+push images, gated GKE deploy |

## Data flow: train → serve

1. **Train** (`train.py`): generates data, fits a `StandardScaler → GradientBoostingClassifier`
   pipeline, logs params/metrics/artifacts + a model signature to MLflow, registers a new
   **version** of `churn-classifier`, and assigns it the `staging` alias.
2. **Evaluate/gate** (`evaluate.py`): loads the `staging` version, scores it on a fresh
   held-out set, and — only if `accuracy ≥ min` and `f1 ≥ min` — moves the `champion` alias
   onto that version. Otherwise it tags the version `rejected` and leaves `champion` untouched.
3. **Build/deploy** (CI): container images are built, scanned with Trivy, pushed, and the
   Helm release is upgraded on GKE (environment-gated).
4. **Serve** (`main.py`): on startup the pod loads `models:/churn-classifier@champion`. If the
   registry is unreachable it may fall back to a local model (configurable). `/ready` reports
   503 until a model is loaded so Kubernetes keeps traffic away.
5. **Observe**: the API exposes Prometheus metrics; Prometheus scrapes `/metrics`; Grafana
   visualises request rate, latency percentiles, error rate, and prediction distribution.

## Model lifecycle (alias transitions)

```mermaid
stateDiagram-v2
    [*] --> staging: train.py registers new version
    staging --> champion: evaluate.py passes gate
    staging --> rejected: evaluate.py fails gate
    champion --> archived: newer version promoted
    archived --> champion: rollback (re-point alias)
```

Aliases (not the deprecated stage strings) drive the lifecycle. Because moving an alias is
atomic and instantaneous, **rollback is simply re-pointing `champion` at a previous version**,
followed by a `POST /reload` (or pod restart) on the API. See the README "Failure & rollback"
section.
