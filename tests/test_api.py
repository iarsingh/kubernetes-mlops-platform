"""API tests using FastAPI's TestClient with a real (tiny) model injected."""

from __future__ import annotations

from src.common.schema import FEATURE_NAMES


def _valid_instance() -> dict:
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


def test_health_is_ok(loaded_api):
    resp = loaded_api.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_ready_reports_loaded_model(loaded_api):
    resp = loaded_api.get("/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert body["model_version"] == "test-1"


def test_predict_returns_valid_predictions(loaded_api):
    resp = loaded_api.post("/predict", json={"instances": [_valid_instance()]})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["predictions"]) == 1
    pred = body["predictions"][0]
    assert pred["predicted_class"] in (0, 1)
    assert pred["predicted_label"] in ("retained", "churned")
    assert 0.0 <= pred["churn_probability"] <= 1.0
    assert body["model_source"] == "local"


def test_predict_batch(loaded_api):
    instances = [_valid_instance(), _valid_instance()]
    resp = loaded_api.post("/predict", json={"instances": instances})
    assert resp.status_code == 200
    assert len(resp.json()["predictions"]) == 2


def test_predict_missing_feature_is_422(loaded_api):
    bad = _valid_instance()
    del bad["monthly_charges"]
    resp = loaded_api.post("/predict", json={"instances": [bad]})
    assert resp.status_code == 422
    assert "monthly_charges" in resp.json()["detail"]


def test_predict_out_of_range_is_422(loaded_api):
    bad = _valid_instance()
    bad["is_premium"] = 5.0  # spec range is [0, 1]
    resp = loaded_api.post("/predict", json={"instances": [bad]})
    assert resp.status_code == 422


def test_metrics_endpoint_exposes_prometheus(loaded_api):
    # Generate at least one prediction so counters are populated.
    loaded_api.post("/predict", json={"instances": [_valid_instance()]})
    resp = loaded_api.get("/metrics")
    assert resp.status_code == 200
    assert "ml_predictions_total" in resp.text
    assert "ml_prediction_latency_seconds" in resp.text


def test_root_lists_features(loaded_api):
    resp = loaded_api.get("/")
    assert resp.status_code == 200
    assert resp.json()["features"] == FEATURE_NAMES
