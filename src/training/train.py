"""Train the churn classifier and register it in the MLflow Model Registry.

What this script does
---------------------
1. Generates a reproducible synthetic dataset (see ``src/common/dataset.py``).
2. Trains a scikit-learn ``Pipeline`` (scaler + gradient-boosted trees).
3. Evaluates on a held-out test split and logs params / metrics / artifacts
   (confusion matrix, ROC data, the input example and signature) to MLflow.
4. Registers the fitted model in the MLflow Model Registry under
   :data:`REGISTERED_MODEL_NAME`, creating a new **version**.
5. Assigns the ``staging`` alias to the freshly trained version so that
   ``evaluate.py`` can pick it up and gate its promotion to ``champion``.

Run locally::

    export MLFLOW_TRACKING_URI=http://localhost:5000   # the docker-compose MLflow
    python -m src.training.train

For a zero-server run, point the tracking URI at a local SQLite database
(MLflow 3.x requires a database backend; the legacy ``./mlruns`` file store is
deprecated)::

    export MLFLOW_TRACKING_URI=sqlite:///mlflow.db
    python -m src.training.train
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import tempfile
from pathlib import Path

import mlflow
import mlflow.sklearn
import numpy as np
from mlflow.models.signature import infer_signature
from mlflow.tracking import MlflowClient
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.common.dataset import generate_dataset
from src.common.schema import (
    FEATURE_NAMES,
    REGISTERED_MODEL_NAME,
    TARGET_NAME,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
)
logger = logging.getLogger("train")

# Alias assigned to a newly trained version, before it has passed evaluation.
STAGING_ALIAS = "staging"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train the churn classifier.")
    parser.add_argument("--n-samples", type=int, default=8_000)
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--n-estimators", type=int, default=200)
    parser.add_argument("--learning-rate", type=float, default=0.05)
    parser.add_argument("--max-depth", type=int, default=3)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--experiment-name",
        default=os.getenv("MLFLOW_EXPERIMENT_NAME", "churn-classifier"),
    )
    parser.add_argument(
        "--register",
        action="store_true",
        default=os.getenv("MLFLOW_REGISTER_MODEL", "true").lower() == "true",
        help="Register the model in the MLflow Model Registry.",
    )
    return parser.parse_args(argv)


def build_model(args: argparse.Namespace) -> Pipeline:
    """Assemble the scikit-learn training pipeline."""
    return Pipeline(
        steps=[
            ("scaler", StandardScaler()),
            (
                "clf",
                GradientBoostingClassifier(
                    n_estimators=args.n_estimators,
                    learning_rate=args.learning_rate,
                    max_depth=args.max_depth,
                    random_state=args.seed,
                ),
            ),
        ]
    )


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray, y_prob: np.ndarray) -> dict:
    """Compute the classification metrics we track for every run."""
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "roc_auc": float(roc_auc_score(y_true, y_prob)),
    }


def _log_json_artifact(obj: dict, filename: str) -> None:
    """Write a dict as a JSON artifact and log it to the active MLflow run."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / filename
        path.write_text(json.dumps(obj, indent=2))
        mlflow.log_artifact(str(path))


def register_model_version(model_uri: str) -> str:
    """Register ``model_uri`` and tag the new version with the staging alias.

    Returns the version string that was created.
    """
    client = MlflowClient()
    # Ensure the registered model container exists (idempotent).
    try:
        client.create_registered_model(REGISTERED_MODEL_NAME)
        logger.info("Created registered model %s", REGISTERED_MODEL_NAME)
    except mlflow.exceptions.MlflowException:
        logger.info("Registered model %s already exists", REGISTERED_MODEL_NAME)

    result = mlflow.register_model(model_uri=model_uri, name=REGISTERED_MODEL_NAME)
    version = result.version
    # Alias-based lifecycle (the modern replacement for deprecated stages).
    client.set_registered_model_alias(REGISTERED_MODEL_NAME, STAGING_ALIAS, version)
    client.set_model_version_tag(
        REGISTERED_MODEL_NAME, version, "validation_status", "pending"
    )
    logger.info(
        "Registered %s v%s and set alias '%s'",
        REGISTERED_MODEL_NAME,
        version,
        STAGING_ALIAS,
    )
    return version


def main(argv: list[str] | None = None) -> dict:
    args = parse_args(argv)
    mlflow.set_experiment(args.experiment_name)

    logger.info("Generating dataset (n=%d)", args.n_samples)
    frame = generate_dataset(n_samples=args.n_samples, seed=args.seed)
    X = frame[FEATURE_NAMES]
    y = frame[TARGET_NAME]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=args.test_size, random_state=args.seed, stratify=y
    )

    with mlflow.start_run() as run:
        logger.info("MLflow run_id=%s", run.info.run_id)
        mlflow.set_tag("stage", "training")
        mlflow.log_params(
            {
                "n_samples": args.n_samples,
                "test_size": args.test_size,
                "n_estimators": args.n_estimators,
                "learning_rate": args.learning_rate,
                "max_depth": args.max_depth,
                "seed": args.seed,
                "model_type": "GradientBoostingClassifier",
                "n_features": len(FEATURE_NAMES),
            }
        )

        model = build_model(args)
        model.fit(X_train, y_train)

        y_pred = model.predict(X_test)
        y_prob = model.predict_proba(X_test)[:, 1]
        metrics = compute_metrics(y_test.to_numpy(), y_pred, y_prob)
        mlflow.log_metrics(metrics)
        logger.info("Test metrics: %s", metrics)

        # Artifacts: confusion matrix and metrics snapshot.
        cm = confusion_matrix(y_test, y_pred).tolist()
        _log_json_artifact(
            {"confusion_matrix": cm, "labels": [0, 1]}, "confusion_matrix.json"
        )
        _log_json_artifact(metrics, "test_metrics.json")

        # Model signature + input example make the served model self-describing.
        signature = infer_signature(X_train, model.predict(X_train))
        input_example = X_train.head(3)

        mlflow.sklearn.log_model(
            sk_model=model,
            name="model",
            signature=signature,
            input_example=input_example,
        )
        model_uri = f"runs:/{run.info.run_id}/model"

        version = None
        if args.register:
            version = register_model_version(model_uri)

        result = {
            "run_id": run.info.run_id,
            "model_uri": model_uri,
            "metrics": metrics,
            "registered_version": version,
        }
        logger.info("Training complete: %s", result)
        return result


if __name__ == "__main__":  # pragma: no cover
    main()
