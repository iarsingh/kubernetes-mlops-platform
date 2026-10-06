"""Unit tests for the training logic (model building + metrics).

These avoid touching MLflow by calling the pure functions directly.
"""

from __future__ import annotations

import argparse

import numpy as np

from src.common.dataset import generate_dataset
from src.common.schema import FEATURE_NAMES, TARGET_NAME
from src.training.train import build_model, compute_metrics


def _args(**overrides) -> argparse.Namespace:
    base = {"n_estimators": 50, "learning_rate": 0.1, "max_depth": 3, "seed": 42}
    base.update(overrides)
    return argparse.Namespace(**base)


def test_build_model_is_a_fittable_pipeline():
    model = build_model(_args())
    frame = generate_dataset(n_samples=800, seed=11)
    X, y = frame[FEATURE_NAMES], frame[TARGET_NAME]
    model.fit(X, y)
    preds = model.predict(X.head(5))
    assert len(preds) == 5
    assert set(np.unique(preds)).issubset({0, 1})


def test_model_learns_signal_above_baseline():
    """A trained model should beat the majority-class baseline on held-out data."""
    from sklearn.model_selection import train_test_split

    frame = generate_dataset(n_samples=3_000, seed=13)
    X, y = frame[FEATURE_NAMES], frame[TARGET_NAME]
    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.25, random_state=13, stratify=y
    )
    model = build_model(_args(n_estimators=120))
    model.fit(X_tr, y_tr)
    y_pred = model.predict(X_te)
    y_prob = model.predict_proba(X_te)[:, 1]
    metrics = compute_metrics(y_te.to_numpy(), y_pred, y_prob)

    baseline = max(y_te.mean(), 1 - y_te.mean())
    assert metrics["accuracy"] > baseline
    assert metrics["roc_auc"] > 0.7


def test_compute_metrics_keys_and_ranges():
    y_true = np.array([0, 1, 1, 0, 1])
    y_pred = np.array([0, 1, 0, 0, 1])
    y_prob = np.array([0.1, 0.9, 0.4, 0.2, 0.8])
    m = compute_metrics(y_true, y_pred, y_prob)
    assert set(m) == {"accuracy", "precision", "recall", "f1", "roc_auc"}
    for v in m.values():
        assert 0.0 <= v <= 1.0
