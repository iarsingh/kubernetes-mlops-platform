"""Shared pytest fixtures.

The key fixture ``loaded_api`` trains a tiny real scikit-learn pipeline in
memory and injects it into the inference service's model cache. This lets the
API tests exercise the *real* ``/predict`` code path (validation, vectorisation,
metrics) without needing MLflow or a network connection.
"""

from __future__ import annotations

import pytest
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.common.dataset import generate_dataset
from src.common.schema import FEATURE_NAMES, TARGET_NAME


@pytest.fixture(scope="session")
def trained_pipeline() -> Pipeline:
    """A small, fast, real model trained on the synthetic dataset."""
    frame = generate_dataset(n_samples=1_500, seed=7)
    X = frame[FEATURE_NAMES]
    y = frame[TARGET_NAME]
    pipe = Pipeline(
        steps=[
            ("scaler", StandardScaler()),
            ("clf", RandomForestClassifier(n_estimators=30, random_state=7)),
        ]
    )
    pipe.fit(X, y)
    return pipe


@pytest.fixture()
def loaded_api(trained_pipeline):
    """A FastAPI TestClient with the trained model injected into the cache."""
    from fastapi.testclient import TestClient

    from src.inference import model_loader
    from src.inference.main import app

    model_loader.reset_cache()
    model_loader._CACHE = model_loader.LoadedModel(
        model=trained_pipeline,
        source="local",
        version="test-1",
        metadata={"origin": "pytest"},
    )
    with TestClient(app) as client:
        yield client
    model_loader.reset_cache()
