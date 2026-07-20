"""Unit tests for the synthetic dataset generator."""

from __future__ import annotations

import pandas as pd

from src.common.dataset import generate_dataset
from src.common.schema import FEATURE_NAMES, TARGET_NAME


def test_dataset_shape_and_columns():
    frame = generate_dataset(n_samples=500, seed=1)
    assert len(frame) == 500
    assert list(frame.columns) == FEATURE_NAMES + [TARGET_NAME]


def test_dataset_is_deterministic():
    a = generate_dataset(n_samples=300, seed=99)
    b = generate_dataset(n_samples=300, seed=99)
    pd.testing.assert_frame_equal(a, b)


def test_dataset_target_is_binary_and_mixed():
    frame = generate_dataset(n_samples=2_000, seed=3)
    values = set(frame[TARGET_NAME].unique())
    assert values.issubset({0, 1})
    # Both classes should be present for a learnable problem.
    assert len(values) == 2


def test_feature_ranges_are_non_negative():
    frame = generate_dataset(n_samples=1_000, seed=5)
    for col in FEATURE_NAMES:
        assert frame[col].min() >= 0
