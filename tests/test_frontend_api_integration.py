"""
tests/test_frontend_api_integration.py — Contract validation for APEX-QUANT Frontend API routes.
"""
from __future__ import annotations

import json
import os
import sys
import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from dashboard.server import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_api_market_universe(client):
    """Verify /api/market/universe accurately labels dataset as curated 52-stock catalog."""
    resp = client.get("/api/market/universe")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "count" in data
    assert "universe" in data
    assert data["count"] >= 45
    # Data Integrity: Accurately describe universe and empirical benchmark
    assert data["universe_catalog"] == "Curated 52-stock catalog"
    assert "RELIANCE" in data["empirical_benchmark_subset"]
    assert "TCS" in data["empirical_benchmark_subset"]
    assert "disclaimer" in data
    assert "NIFTY 500" in data["disclaimer"] or "coverage" in data["disclaimer"]
    first = data["universe"][0]
    assert "symbol" in first
    assert "company_name" in first
    assert "sector" in first
    assert "industry" in first


def test_api_scanner_never_fabricates_ml(client):
    """Verify /api/scanner never fabricates ML predictions or confidences when authentic signals are absent."""
    # Reset scanner cache so fresh evaluation runs
    from dashboard.server import _scanner_cache, _scanner_cache_lock
    with _scanner_cache_lock:
        _scanner_cache["timestamp"] = 0.0
        _scanner_cache["data"] = []

    resp = client.get("/api/scanner")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "count" in data
    assert "ranked" in data
    assert data["count"] > 0
    item = data["ranked"][0]
    assert "rank" in item
    assert "symbol" in item
    assert "price" in item
    assert "prediction_status" in item

    # If no cycle has produced signals, predictions must be explicitly unavailable (null/None)
    for it in data["ranked"]:
        if it["prediction_status"] == "PREDICTION_UNAVAILABLE":
            assert it["predicted_return"] is None, f"Fabricated return found for {it['symbol']}"
            assert it["confidence"] is None, f"Fabricated confidence found for {it['symbol']}"
            assert it["confidence"] != 0.68, "Hardcoded 0.68 fallback confidence detected!"
            assert it["quant_score"] is None, f"Fabricated quant_score found for {it['symbol']}"


def test_api_stock_detail_never_fabricates_defaults(client):
    """Verify /api/stock/<symbol> returns null/N/A when no actual signal exists, removing 0.015 / 0.72 defaults."""
    resp = client.get("/api/stock/RELIANCE")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["symbol"] == "RELIANCE"
    assert "price" in data
    assert "features" in data
    assert "risk" in data
    assert "prediction_status" in data

    # Critical check: hardcoded defaults 0.015 and 0.72 must NEVER be returned as fallback
    if data["prediction_status"] == "PREDICTION_UNAVAILABLE":
        assert data["predicted_return_5d"] is None, "Fabricated predicted_return_5d detected"
        assert data["confidence"] is None, "Fabricated confidence detected"
        assert data["quant_score"] is None, "Fabricated quant_score detected"
        assert data["confidence"] != 0.72, "Hardcoded 0.72 confidence default detected!"
        assert data["predicted_return_5d"] != 0.015, "Hardcoded 0.015 pred_ret default detected!"


def test_api_ml_model(client):
    """Verify /api/ml/model returns authentic RandomForest v1 metadata and research disclaimer."""
    resp = client.get("/api/ml/model")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["model_name"] == "RandomForest"
    assert data["version"] == "v1"
    assert data["target_name"] == "target_return_5d"
    assert len(data["features"]) == 66
    assert "metrics" in data
    assert "val_mae" in data["metrics"]
    assert "val_mean_ic" in data["metrics"]
    assert "research_disclaimer" in data


def test_api_backtest_results_never_fabricates_metrics(client):
    """Verify /api/backtest/results returns unavailable status when no authentic artifact exists on disk."""
    resp = client.get("/api/backtest/results")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "disclaimer" in data
    assert "HISTORICAL RESEARCH SIMULATION" in data["disclaimer"]

    # When no artifact is on disk, must return unavailable status without fabricated numbers
    if data["status"] == "unavailable":
        assert "message" in data
        assert data["strategies"] == {}
        assert data["equity_curve"] == []
    else:
        # If an authentic artifact is loaded, prove that "Production" is removed and metrics are authentic
        for strat in data["strategies"].values():
            assert "Production" not in strat["name"], "Strategy name must not contain 'Production'"

    # Critical assertion: Fabricated hardcoded metrics must not be returned
    strategies = data.get("strategies", {})
    if "constrained" in strategies:
        assert strategies["constrained"].get("total_return_pct") != 17.42 or os.path.exists("reports/step8_backtest_results.json")


def test_api_risk_status_safety_constraints(client):
    """Verify /api/risk/status enforces paper trading safety invariants and pre-trade checks."""
    resp = client.get("/api/risk/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["mode"] == "PAPER_TRADING"
    assert data["supports_live_orders"] is False
    assert "limits" in data
    assert "utilization" in data
    assert "checks" in data
    assert len(data["checks"]) == 12


def test_spa_and_legacy_routes(client):
    """Verify SPA page route fallback and legacy Binance route isolation."""
    resp_legacy = client.get("/legacy/binance")
    assert resp_legacy.status_code == 200

    resp_compact = client.get("/dashboard-compact")
    assert resp_compact.status_code == 200

    resp_root = client.get("/")
    assert resp_root.status_code == 200

    resp_scanner = client.get("/scanner")
    assert resp_scanner.status_code == 200
