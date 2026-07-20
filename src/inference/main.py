"""FastAPI inference service for the churn classifier.

Endpoints
---------
* ``GET  /health``   liveness  — process is up (never touches the model).
* ``GET  /ready``    readiness — model is loaded and can serve predictions.
* ``GET  /metrics``  Prometheus exposition (request count, latency, predictions).
* ``POST /predict``  score one or many feature rows.
* ``POST /reload``   force a model reload from the registry (admin/ops).
* ``GET  /``         service metadata.

The model is loaded on startup, but a failure to load does **not** crash the
process — instead ``/ready`` reports 503 so Kubernetes keeps traffic away until
the model is available (e.g. once MLflow comes back or a champion is promoted).
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from pydantic import BaseModel, Field

from src.common.schema import CLASS_LABELS, FEATURE_NAMES, FEATURE_SPECS
from src.inference.model_loader import (
    ModelLoadError,
    get_cached_model,
    load_model,
    reset_cache,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
)
logger = logging.getLogger("inference")

# --------------------------------------------------------------------------- #
# Prometheus metrics
# --------------------------------------------------------------------------- #
PREDICTIONS_TOTAL = Counter(
    "ml_predictions_total",
    "Total number of predictions served, labelled by predicted class.",
    ["predicted_label"],
)
PREDICTION_ERRORS_TOTAL = Counter(
    "ml_prediction_errors_total",
    "Total number of prediction requests that failed.",
    ["reason"],
)
PREDICTION_LATENCY = Histogram(
    "ml_prediction_latency_seconds",
    "Latency of the /predict handler in seconds.",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
)
PREDICTED_PROBABILITY = Histogram(
    "ml_predicted_probability",
    "Distribution of predicted churn probabilities.",
    buckets=(0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
)
MODEL_LOADED = Gauge(
    "ml_model_loaded",
    "1 if a model is currently loaded and servable, else 0.",
)
MODEL_INFO = Gauge(
    "ml_model_info",
    "Static model provenance (value is always 1; see labels).",
    ["source", "version"],
)


# --------------------------------------------------------------------------- #
# Request / response schemas
# --------------------------------------------------------------------------- #
def _example_features() -> dict:
    """A realistic example payload derived from the feature specs."""
    return {
        "account_age_months": 8.0,
        "monthly_charges": 89.5,
        "total_charges": 716.0,
        "num_support_tickets": 4.0,
        "avg_latency_ms": 320.0,
        "data_usage_gb": 55.2,
        "num_logins_last_30d": 6.0,
        "is_premium": 0.0,
    }


class PredictRequest(BaseModel):
    """A batch of feature rows to score."""

    instances: list[dict[str, float]] = Field(
        ...,
        min_length=1,
        description="List of feature dicts; each must contain all model features.",
        json_schema_extra={"example": [_example_features()]},
    )


class Prediction(BaseModel):
    predicted_class: int
    predicted_label: str
    churn_probability: float


class PredictResponse(BaseModel):
    predictions: list[Prediction]
    model_source: str
    model_version: str | None = None


def _validate_and_vectorize(instances: list[dict[str, float]]) -> list[list[float]]:
    """Validate presence/range of features and build ordered feature rows."""
    rows: list[list[float]] = []
    for i, inst in enumerate(instances):
        missing = [f for f in FEATURE_NAMES if f not in inst]
        if missing:
            raise HTTPException(
                status_code=422,
                detail=f"instance {i} missing features: {missing}",
            )
        row: list[float] = []
        for f in FEATURE_NAMES:
            try:
                val = float(inst[f])
            except (TypeError, ValueError) as exc:
                raise HTTPException(
                    status_code=422,
                    detail=f"instance {i} feature '{f}' is not numeric",
                ) from exc
            spec = FEATURE_SPECS[f]
            if not (spec.minimum <= val <= spec.maximum):
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"instance {i} feature '{f}'={val} out of range "
                        f"[{spec.minimum}, {spec.maximum}]"
                    ),
                )
            row.append(val)
        rows.append(row)
    return rows


# --------------------------------------------------------------------------- #
# Lifespan: load the model on startup (non-fatal on failure)
# --------------------------------------------------------------------------- #
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        loaded = load_model()
        MODEL_LOADED.set(1)
        MODEL_INFO.labels(source=loaded.source, version=str(loaded.version)).set(1)
        logger.info(
            "Model loaded on startup (source=%s version=%s)",
            loaded.source,
            loaded.version,
        )
    except ModelLoadError as exc:
        MODEL_LOADED.set(0)
        logger.error("Startup model load failed; /ready will report 503: %s", exc)
    yield


app = FastAPI(
    title="Churn Classifier Inference API",
    description="Serves the MLflow-registered churn model with Prometheus metrics.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/")
def root() -> dict:
    loaded = get_cached_model()
    return {
        "service": "churn-classifier-inference",
        "version": app.version,
        "model_loaded": loaded is not None,
        "model_source": loaded.source if loaded else None,
        "model_version": loaded.version if loaded else None,
        "features": FEATURE_NAMES,
    }


@app.get("/health")
def health() -> dict:
    """Liveness probe — the process is running. Does not touch the model."""
    return {"status": "ok"}


@app.get("/ready")
def ready(response: Response) -> dict:
    """Readiness probe — a model is loaded and predictions can be served."""
    loaded = get_cached_model()
    if loaded is None:
        response.status_code = 503
        return {"status": "unavailable", "reason": "model not loaded"}
    return {
        "status": "ready",
        "model_source": loaded.source,
        "model_version": loaded.version,
    }


@app.get("/metrics")
def metrics() -> Response:
    """Prometheus metrics exposition endpoint."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/reload")
def reload_model() -> dict:
    """Force a model reload (e.g. after promoting a new champion)."""
    reset_cache()
    try:
        loaded = load_model(force_reload=True)
    except ModelLoadError as exc:
        MODEL_LOADED.set(0)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    MODEL_LOADED.set(1)
    MODEL_INFO.labels(source=loaded.source, version=str(loaded.version)).set(1)
    return {"status": "reloaded", "model_source": loaded.source,
            "model_version": loaded.version}


@app.post("/predict", response_model=PredictResponse)
def predict(request: PredictRequest) -> PredictResponse:
    """Score a batch of feature rows and return per-row churn predictions."""
    start = time.perf_counter()
    loaded = get_cached_model()
    if loaded is None:
        # Lazy load attempt (covers the case where startup failed then recovered).
        try:
            loaded = load_model()
            MODEL_LOADED.set(1)
        except ModelLoadError as exc:
            PREDICTION_ERRORS_TOTAL.labels(reason="model_unavailable").inc()
            raise HTTPException(status_code=503, detail=f"model unavailable: {exc}")

    rows = _validate_and_vectorize(request.instances)

    try:
        import pandas as pd

        frame = pd.DataFrame(rows, columns=FEATURE_NAMES)
        classes = loaded.model.predict(frame)
        probs = loaded.model.predict_proba(frame)[:, 1]
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        PREDICTION_ERRORS_TOTAL.labels(reason="inference_error").inc()
        logger.exception("Inference failed")
        raise HTTPException(status_code=500, detail=f"inference error: {exc}")

    predictions: list[Prediction] = []
    for cls, prob in zip(classes, probs):
        cls_int = int(cls)
        label = CLASS_LABELS.get(cls_int, str(cls_int))
        PREDICTIONS_TOTAL.labels(predicted_label=label).inc()
        PREDICTED_PROBABILITY.observe(float(prob))
        predictions.append(
            Prediction(
                predicted_class=cls_int,
                predicted_label=label,
                churn_probability=round(float(prob), 6),
            )
        )

    PREDICTION_LATENCY.observe(time.perf_counter() - start)
    return PredictResponse(
        predictions=predictions,
        model_source=loaded.source,
        model_version=loaded.version,
    )
