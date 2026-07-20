"""Evaluate a registered model version and gate its promotion.

This is the *model governance* step of the pipeline. It:

1. Loads a specific model version from the MLflow Model Registry (by default the
   version currently carrying the ``staging`` alias).
2. Re-evaluates it on a freshly generated held-out set with a different seed
   (so we are not just re-reading training-time metrics).
3. Logs the evaluation metrics to MLflow.
4. **Gates promotion**: only if accuracy AND f1 clear the configured thresholds
   does it move the ``champion`` (production) alias onto this version. Otherwise
   the version is tagged as ``rejected`` and the current champion is untouched.

Because alias moves are atomic, this doubles as the rollback primitive: pointing
``champion`` back at an older version instantly rolls the served model back.

Run locally::

    python -m src.training.evaluate --min-accuracy 0.75 --min-f1 0.6
"""

from __future__ import annotations

import argparse
import logging
import os

import mlflow
from mlflow.tracking import MlflowClient
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score

from src.common.dataset import generate_dataset
from src.common.schema import (
    FEATURE_NAMES,
    PRODUCTION_ALIAS,
    REGISTERED_MODEL_NAME,
    TARGET_NAME,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
)
logger = logging.getLogger("evaluate")

STAGING_ALIAS = "staging"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate and gate a model version.")
    parser.add_argument(
        "--alias",
        default=STAGING_ALIAS,
        help="Alias of the version to evaluate (default: staging).",
    )
    parser.add_argument("--version", default=None, help="Explicit version to evaluate.")
    parser.add_argument("--min-accuracy", type=float, default=0.72)
    parser.add_argument("--min-f1", type=float, default=0.55)
    parser.add_argument("--eval-samples", type=int, default=4_000)
    parser.add_argument("--seed", type=int, default=1234)
    parser.add_argument(
        "--experiment-name",
        default=os.getenv("MLFLOW_EXPERIMENT_NAME", "churn-classifier"),
    )
    return parser.parse_args(argv)


def resolve_version(client: MlflowClient, args: argparse.Namespace) -> str:
    """Resolve which version to evaluate, from explicit arg or alias."""
    if args.version:
        return str(args.version)
    mv = client.get_model_version_by_alias(REGISTERED_MODEL_NAME, args.alias)
    return mv.version


def evaluate_version(version: str, args: argparse.Namespace) -> dict:
    """Load the version, score it on fresh data, and return metrics."""
    model_uri = f"models:/{REGISTERED_MODEL_NAME}/{version}"
    logger.info("Loading model %s", model_uri)
    model = mlflow.sklearn.load_model(model_uri)

    frame = generate_dataset(n_samples=args.eval_samples, seed=args.seed)
    X = frame[FEATURE_NAMES]
    y = frame[TARGET_NAME].to_numpy()

    y_pred = model.predict(X)
    y_prob = model.predict_proba(X)[:, 1]

    return {
        "eval_accuracy": float(accuracy_score(y, y_pred)),
        "eval_f1": float(f1_score(y, y_pred, zero_division=0)),
        "eval_roc_auc": float(roc_auc_score(y, y_prob)),
    }


def gate_and_promote(
    client: MlflowClient, version: str, metrics: dict, args: argparse.Namespace
) -> bool:
    """Promote to the production alias iff metrics clear the thresholds."""
    passed = (
        metrics["eval_accuracy"] >= args.min_accuracy
        and metrics["eval_f1"] >= args.min_f1
    )
    if passed:
        client.set_registered_model_alias(
            REGISTERED_MODEL_NAME, PRODUCTION_ALIAS, version
        )
        client.set_model_version_tag(
            REGISTERED_MODEL_NAME, version, "validation_status", "approved"
        )
        logger.info(
            "PROMOTED %s v%s to alias '%s' (accuracy=%.3f f1=%.3f)",
            REGISTERED_MODEL_NAME,
            version,
            PRODUCTION_ALIAS,
            metrics["eval_accuracy"],
            metrics["eval_f1"],
        )
    else:
        client.set_model_version_tag(
            REGISTERED_MODEL_NAME, version, "validation_status", "rejected"
        )
        logger.warning(
            "REJECTED %s v%s (accuracy=%.3f<%.3f or f1=%.3f<%.3f). "
            "Champion alias left unchanged.",
            REGISTERED_MODEL_NAME,
            version,
            metrics["eval_accuracy"],
            args.min_accuracy,
            metrics["eval_f1"],
            args.min_f1,
        )
    return passed


def main(argv: list[str] | None = None) -> dict:
    args = parse_args(argv)
    mlflow.set_experiment(args.experiment_name)
    client = MlflowClient()

    version = resolve_version(client, args)
    logger.info("Evaluating %s version %s", REGISTERED_MODEL_NAME, version)

    with mlflow.start_run(run_name=f"evaluate-v{version}"):
        mlflow.set_tag("stage", "evaluation")
        mlflow.log_param("evaluated_version", version)
        mlflow.log_params(
            {"min_accuracy": args.min_accuracy, "min_f1": args.min_f1}
        )
        metrics = evaluate_version(version, args)
        mlflow.log_metrics(metrics)
        promoted = gate_and_promote(client, version, metrics, args)
        mlflow.set_tag("promoted", str(promoted))

    return {"version": version, "metrics": metrics, "promoted": promoted}


if __name__ == "__main__":  # pragma: no cover
    result = main()
    # Non-zero exit if the gate failed, so CI can react.
    raise SystemExit(0 if result["promoted"] else 1)
