"""Deterministic synthetic dataset generator for the churn classifier.

We deliberately generate the data in code (rather than shipping a CSV) so the
whole pipeline is reproducible from a single seed and has no external data
dependency. The generative process encodes a plausible signal:

* Customers with many support tickets and high latency churn more.
* Long-tenured, premium, highly-engaged customers churn less.

A little label noise is injected so the problem is non-trivial and the reported
metrics look like a real model rather than a perfect separator.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .schema import FEATURE_NAMES, TARGET_NAME


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
    total_charges = (monthly_charges * account_age_months) * rng.uniform(
        0.8, 1.2, size=n_samples
    )
    num_support_tickets = rng.poisson(1.5, size=n_samples).clip(0, 100)
    avg_latency_ms = rng.normal(180, 90, size=n_samples).clip(1, 5_000)
    data_usage_gb = rng.gamma(shape=2.0, scale=40.0, size=n_samples).clip(0, 10_000)
    num_logins_last_30d = rng.poisson(20, size=n_samples).clip(0, 1_000)
    is_premium = rng.binomial(1, 0.35, size=n_samples).astype(float)

    # Latent churn "risk" score built from standardised drivers.
    risk = (
        0.9 * _z(num_support_tickets)
        + 0.7 * _z(avg_latency_ms)
        - 0.8 * _z(account_age_months)
        - 0.6 * _z(num_logins_last_30d)
        - 0.5 * is_premium
        + 0.3 * _z(monthly_charges)
    )
    # Convert to probability and sample labels (with implicit noise from Bernoulli).
    prob = 1.0 / (1.0 + np.exp(-risk))
    churned = rng.binomial(1, prob)

    frame = pd.DataFrame(
        {
            "account_age_months": account_age_months,
            "monthly_charges": monthly_charges,
            "total_charges": total_charges,
            "num_support_tickets": num_support_tickets.astype(float),
            "avg_latency_ms": avg_latency_ms,
            "data_usage_gb": data_usage_gb,
            "num_logins_last_30d": num_logins_last_30d.astype(float),
            "is_premium": is_premium,
        }
    )
    # Guarantee column order matches the schema contract.
    frame = frame[FEATURE_NAMES]
    frame[TARGET_NAME] = churned.astype(int)
    return frame


def _z(values: np.ndarray) -> np.ndarray:
    """Standardise an array to zero mean / unit variance (safe for constants)."""
    std = values.std()
    if std == 0:
        return np.zeros_like(values, dtype=float)
    return (values - values.mean()) / std
