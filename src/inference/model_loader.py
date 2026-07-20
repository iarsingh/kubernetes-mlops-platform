"""Load the production model for the inference service.

Resolution order
----------------
1. **MLflow Model Registry** (preferred): load the version currently carrying
   the ``champion`` alias from ``models:/churn-classifier@champion``. This is
   the same alias ``evaluate.py`` promotes to, so serving always follows the
   governed lifecycle.
2. **Local file fallback**: if MLflow is unreachable (no ``MLFLOW_TRACKING_URI``,
   network error, or the alias does not exist yet) *and* a local model artifact
   is present at ``$LOCAL_MODEL_PATH`` (default ``./artifacts/model``), load that
   instead. This keeps the API serviceable in air-gapped / demo environments and
   during MLflow outages, at the cost of not auto-tracking new promotions.

The fallback is deliberate and documented: in production you would prefer to
fail readiness (so Kubernetes keeps the old pod serving) rather than silently
serve a stale local model, but for a portfolio/demo the fallback lets a reviewer
run the API with zero infrastructure. Set ``ALLOW_LOCAL_FALLBACK=false`` to make
the loader raise instead of falling back.
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from typing import Any

from src.common.schema import PRODUCTION_ALIAS, REGISTERED_MODEL_NAME

logger = logging.getLogger("model_loader")


@dataclass
class LoadedModel:
    """Wrapper around a loaded model plus provenance metadata."""

    model: Any
    source: str  # "registry" or "local"
    version: str | None = None
    alias: str | None = None
    metadata: dict = field(default_factory=dict)


class ModelLoadError(RuntimeError):
    """Raised when no model could be loaded from any source."""


_LOCK = threading.Lock()
_CACHE: LoadedModel | None = None


def _load_from_registry() -> LoadedModel:
    """Load ``models:/<name>@<alias>`` from the MLflow Model Registry."""
    import mlflow  # imported lazily so the API can start without mlflow configured
    import mlflow.sklearn
    from mlflow.tracking import MlflowClient

    uri = f"models:/{REGISTERED_MODEL_NAME}@{PRODUCTION_ALIAS}"
    logger.info("Loading model from registry: %s", uri)
    model = mlflow.sklearn.load_model(uri)

    version = None
    try:
        client = MlflowClient()
        mv = client.get_model_version_by_alias(REGISTERED_MODEL_NAME, PRODUCTION_ALIAS)
        version = mv.version
    except Exception:  # noqa: BLE001 - version metadata is best-effort
        logger.debug("Could not resolve version for alias %s", PRODUCTION_ALIAS)

    return LoadedModel(
        model=model,
        source="registry",
        version=version,
        alias=PRODUCTION_ALIAS,
        metadata={"uri": uri},
    )


def _load_from_local() -> LoadedModel:
    """Load an MLflow-format model saved on the local filesystem."""
    import mlflow.sklearn

    path = os.getenv("LOCAL_MODEL_PATH", "./artifacts/model")
    if not os.path.exists(path):
        raise ModelLoadError(
            f"No local model at '{path}'. Run training with "
            "MLFLOW_TRACKING_URI unset to populate ./mlruns, or export a model "
            "to LOCAL_MODEL_PATH."
        )
    logger.warning("Loading model from LOCAL FALLBACK path: %s", path)
    model = mlflow.sklearn.load_model(path)
    return LoadedModel(
        model=model, source="local", version=None, metadata={"path": path}
    )


def load_model(force_reload: bool = False) -> LoadedModel:
    """Return the served model, loading (and caching) it on first use.

    Registry first, then local fallback (unless ``ALLOW_LOCAL_FALLBACK=false``).
    Thread-safe and idempotent.
    """
    global _CACHE
    with _LOCK:
        if _CACHE is not None and not force_reload:
            return _CACHE

        allow_fallback = os.getenv("ALLOW_LOCAL_FALLBACK", "true").lower() == "true"
        registry_error: Exception | None = None

        try:
            _CACHE = _load_from_registry()
            return _CACHE
        except Exception as exc:  # noqa: BLE001 - we intentionally degrade
            registry_error = exc
            logger.warning("Registry load failed: %s", exc)

        if allow_fallback:
            try:
                _CACHE = _load_from_local()
                return _CACHE
            except Exception as exc:  # noqa: BLE001
                raise ModelLoadError(
                    f"Registry load failed ({registry_error}); "
                    f"local fallback also failed ({exc})."
                ) from exc

        raise ModelLoadError(
            f"Registry load failed and local fallback disabled: {registry_error}"
        )


def get_cached_model() -> LoadedModel | None:
    """Return the cached model without triggering a load (used by /ready)."""
    return _CACHE


def reset_cache() -> None:
    """Clear the cache (used by tests and the /reload admin path)."""
    global _CACHE
    with _LOCK:
        _CACHE = None
