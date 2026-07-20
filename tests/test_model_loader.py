"""Tests for the model loader, including a mocked MLflow registry path."""

from __future__ import annotations

import sys
import types
from unittest import mock

import pytest

import src.inference.model_loader as ml
from src.common.schema import PRODUCTION_ALIAS, REGISTERED_MODEL_NAME


@pytest.fixture(autouse=True)
def _clean_cache():
    ml.reset_cache()
    yield
    ml.reset_cache()


def _install_fake_mlflow(load_model_return, alias_version="5"):
    """Install fake ``mlflow`` and ``mlflow.sklearn`` / ``mlflow.tracking`` modules.

    Returns the created module objects so tests can assert on the mocks.
    """
    fake_mlflow = types.ModuleType("mlflow")
    fake_sklearn = types.ModuleType("mlflow.sklearn")
    fake_tracking = types.ModuleType("mlflow.tracking")

    fake_sklearn.load_model = mock.MagicMock(return_value=load_model_return)
    fake_mlflow.sklearn = fake_sklearn

    fake_mv = mock.MagicMock()
    fake_mv.version = alias_version
    client = mock.MagicMock()
    client.get_model_version_by_alias.return_value = fake_mv
    fake_tracking.MlflowClient = mock.MagicMock(return_value=client)

    return {
        "mlflow": fake_mlflow,
        "mlflow.sklearn": fake_sklearn,
        "mlflow.tracking": fake_tracking,
        "client": client,
    }


def test_load_from_registry_uses_alias(monkeypatch):
    sentinel_model = object()
    fakes = _install_fake_mlflow(sentinel_model, alias_version="7")
    monkeypatch.setitem(sys.modules, "mlflow", fakes["mlflow"])
    monkeypatch.setitem(sys.modules, "mlflow.sklearn", fakes["mlflow.sklearn"])
    monkeypatch.setitem(sys.modules, "mlflow.tracking", fakes["mlflow.tracking"])

    loaded = ml.load_model(force_reload=True)

    assert loaded.source == "registry"
    assert loaded.version == "7"
    assert loaded.alias == PRODUCTION_ALIAS
    # The registry URI must reference the alias, not a hardcoded version.
    expected_uri = f"models:/{REGISTERED_MODEL_NAME}@{PRODUCTION_ALIAS}"
    fakes["mlflow.sklearn"].load_model.assert_called_once_with(expected_uri)


def test_registry_failure_falls_back_to_local(monkeypatch, tmp_path):
    # Registry raises on load.
    fake_mlflow = types.ModuleType("mlflow")
    fake_sklearn = types.ModuleType("mlflow.sklearn")
    fake_tracking = types.ModuleType("mlflow.tracking")

    # Registry path raises, local path returns a sentinel from a real dir.
    local_model = object()

    def _load(uri):
        if uri.startswith("models:/"):
            raise RuntimeError("registry down")
        return local_model

    fake_sklearn.load_model = mock.MagicMock(side_effect=_load)
    fake_mlflow.sklearn = fake_sklearn
    fake_tracking.MlflowClient = mock.MagicMock()

    monkeypatch.setitem(sys.modules, "mlflow", fake_mlflow)
    monkeypatch.setitem(sys.modules, "mlflow.sklearn", fake_sklearn)
    monkeypatch.setitem(sys.modules, "mlflow.tracking", fake_tracking)

    # Point the local fallback at an existing directory.
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    monkeypatch.setenv("LOCAL_MODEL_PATH", str(model_dir))
    monkeypatch.setenv("ALLOW_LOCAL_FALLBACK", "true")

    loaded = ml.load_model(force_reload=True)
    assert loaded.source == "local"
    assert loaded.model is local_model


def test_no_fallback_raises_when_disabled(monkeypatch):
    fake_mlflow = types.ModuleType("mlflow")
    fake_sklearn = types.ModuleType("mlflow.sklearn")
    fake_sklearn.load_model = mock.MagicMock(side_effect=RuntimeError("registry down"))
    fake_mlflow.sklearn = fake_sklearn

    monkeypatch.setitem(sys.modules, "mlflow", fake_mlflow)
    monkeypatch.setitem(sys.modules, "mlflow.sklearn", fake_sklearn)
    monkeypatch.setenv("ALLOW_LOCAL_FALLBACK", "false")

    with pytest.raises(ml.ModelLoadError):
        ml.load_model(force_reload=True)


def test_cache_returns_same_instance():
    sentinel = ml.LoadedModel(model=object(), source="local", version="1")
    ml._CACHE = sentinel
    assert ml.load_model() is sentinel
    assert ml.get_cached_model() is sentinel
