"""Single source of truth for the model's feature schema.

Both the training pipeline (``src/training``) and the inference service
(``src/inference``) import from this module so that the feature contract can
never drift between how the model is trained and how it is served.

Business context
----------------
The demo model predicts **customer churn** for a subscription product from a
small set of tabular account / usage signals. The features are intentionally
human-readable so the ``/predict`` API contract is self-documenting.
"""

from __future__ import annotations

from dataclasses import dataclass

# Ordered list of feature names. Order matters: the model is trained on a
# DataFrame with these columns in this exact order, and inference rebuilds the
# feature vector in the same order.
FEATURE_NAMES: list[str] = [
    "account_age_months",
    "monthly_charges",
    "total_charges",
    "num_support_tickets",
    "avg_latency_ms",
    "data_usage_gb",
    "num_logins_last_30d",
    "is_premium",
]

# Human-friendly target label.
TARGET_NAME = "churned"

# Class index -> label mapping used in API responses.
CLASS_LABELS: dict[int, str] = {0: "retained", 1: "churned"}


@dataclass(frozen=True)
class FeatureSpec:
    """Metadata for a single feature (used for validation and docs)."""

    name: str
    dtype: str
    minimum: float
    maximum: float
    description: str


# Reasonable domain ranges used for lightweight input validation and for
# generating realistic-looking example payloads in the API docs.
FEATURE_SPECS: dict[str, FeatureSpec] = {
    "account_age_months": FeatureSpec(
        "account_age_months",
        "float",
        0,
        240,
        "How long the customer has held the account, in months.",
    ),
    "monthly_charges": FeatureSpec(
        "monthly_charges",
        "float",
        0,
        500,
        "Current monthly recurring charge in USD.",
    ),
    "total_charges": FeatureSpec(
        "total_charges",
        "float",
        0,
        100_000,
        "Lifetime total charges billed to the customer in USD.",
    ),
    "num_support_tickets": FeatureSpec(
        "num_support_tickets",
        "float",
        0,
        100,
        "Number of support tickets opened in the last 90 days.",
    ),
    "avg_latency_ms": FeatureSpec(
        "avg_latency_ms",
        "float",
        0,
        5_000,
        "Average request latency the customer experienced, in ms.",
    ),
    "data_usage_gb": FeatureSpec(
        "data_usage_gb",
        "float",
        0,
        10_000,
        "Data consumed in the last billing period, in GB.",
    ),
    "num_logins_last_30d": FeatureSpec(
        "num_logins_last_30d",
        "float",
        0,
        1_000,
        "Distinct login sessions in the last 30 days (engagement signal).",
    ),
    "is_premium": FeatureSpec(
        "is_premium",
        "float",
        0,
        1,
        "Whether the customer is on a premium plan (1) or not (0).",
    ),
}

# Name under which the model is registered in the MLflow Model Registry.
REGISTERED_MODEL_NAME = "churn-classifier"

# Alias used to mark the model version that inference should serve.
PRODUCTION_ALIAS = "champion"
