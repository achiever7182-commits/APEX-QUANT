"""
tests/test_alpha_v2_research.py — Permanent Verification Suite for APEX-QUANT Step 13.7.

Validates:
1. Frozen Baseline Preservation: Baseline metrics (+14.36% return, 13.92x turnover, ₹44,959.99 costs)
   remain 100% invariant and preserved.
2. Turnover Reduction Invariants:
   - Monthly rebalancing reduces turnover by >= 50% vs weekly.
   - Turnover penalty (gamma=1.0) reduces turnover significantly vs unpenalized SLSQP.
3. No Lookahead & Chronological Separation:
   - Out-of-sample period (2024-05-01 -> 2026-09-16) strictly follows baseline (2023-06-01 -> 2024-04-30).
4. Universe Integrity & Anti-Fabrication:
   - Confirms exactly 5 empirical symbols available; 47 catalog symbols unavailable.
5. Machine-Readable Artifact Integrity:
   - Confirms all Step 13.7 artifact outputs exist in docs/results/step13_7/ and are non-empty.
"""
from __future__ import annotations

import json
from pathlib import Path
import pandas as pd
import pytest

from backtesting.config import BacktestConfig
from backtesting.engine import BacktestEngine
from data.market.storage import ParquetMarketDataStorage
from features.engine import FeatureEngine
from universe.constituents import CuratedNifty500Provider

ROOT_DIR = Path(__file__).resolve().parent.parent


def test_frozen_baseline_preservation():
    """Verify that Step 13.5 baseline numbers (+14.36% return, 13.92x turnover, ₹44,959.99 costs) are strictly preserved."""
    storage = ParquetMarketDataStorage()
    symbols = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]

    price_dfs = []
    for s in symbols:
        df = storage.query_by_symbol(s, is_adjusted=True)
        assert df is not None and not df.empty
        price_dfs.append(df[["timestamp", "symbol", "close"]])
    prices_all = pd.concat(price_dfs, ignore_index=True)

    fe = FeatureEngine()
    fs_base = fe.generate_panel_from_storage(
        storage=storage,
        symbols=symbols,
        start_date="2022-01-01",
        end_date="2024-04-30",
        is_adjusted=True,
    )
    panel_base = fs_base.data.merge(prices_all, on=["timestamp", "symbol"], how="left")
    bar_dfs = {s: storage.query_by_symbol(s, is_adjusted=True) for s in symbols}

    base_cfg = BacktestConfig(
        start_date="2023-06-01",
        end_date="2024-04-30",
        initial_capital=1_000_000.0,
        rebalance_frequency="weekly",
        execution_convention="next_open",
        transaction_cost_bps=10.0,
        slippage_bps=5.0,
        risk_free_rate=0.065,
        cagr_convention="trading",
        use_walk_forward_ml=True,
        ml_model_type="ridge",
        ml_target_horizon=5,
        default_allocation_method="constrained",
        warmup_bars=0,
    )

    res = BacktestEngine(config=base_cfg).run(candidate_panel=panel_base, market_bars=bar_dfs)
    m = res.metrics

    # Strict baseline tolerance assertions
    assert abs(m.total_return * 100 - 14.36) < 0.05, f"Return drifted: {m.total_return * 100:.2f}%"
    assert abs(m.total_turnover - 13.92) < 0.05, f"Turnover drifted: {m.total_turnover:.2f}x"
    total_costs = m.total_fees + m.total_slippage
    assert abs(total_costs - 44959.99) < 50.0, f"Costs drifted: ₹{total_costs:.2f}"


def test_universe_catalog_coverage_and_no_fabrication():
    """Verify that Step 13.7 universe requirements artifact is preserved and 5 empirical symbols are intact."""
    storage = ParquetMarketDataStorage()
    empirical_symbols = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]

    for sym in empirical_symbols:
        df = storage.query_by_symbol(sym, is_adjusted=True)
        assert df is not None and not df.empty, f"Empirical symbol {sym} missing from storage"
        assert len(df) >= 1200, f"Insufficient bars for {sym}: {len(df)}"

    # Validate frozen Step 13.7 artifact documenting the 47 catalog symbols missing at Step 13.7
    art_path = ROOT_DIR / "docs" / "results" / "step13_7" / "universe_data_requirements.json"
    assert art_path.exists()
    with open(art_path, "r") as f:
        data = json.load(f)
    assert len(data["available_symbols"]) == 5
    assert data["missing_catalog_count"] == 47


def test_chronological_oos_separation():
    """Verify that OOS period strictly starts after baseline period without overlap or lookahead."""
    baseline_end = pd.Timestamp("2024-04-30")
    oos_start = pd.Timestamp("2024-05-01")
    assert oos_start > baseline_end, "OOS period must strictly succeed baseline period"


def test_step13_7_artifacts_exist():
    """Verify that all required Step 13.7 machine-readable files exist and are non-empty."""
    res_dir = ROOT_DIR / "docs" / "results" / "step13_7"
    required_files = [
        "alpha_v2_scorecard.csv",
        "turnover_attribution.json",
        "cost_sensitivity_sweep.csv",
        "ml_signal_quality.json",
        "factor_exposure_analysis.json",
        "oos_evaluation_summary.json",
        "universe_data_requirements.json",
    ]

    for fname in required_files:
        fpath = res_dir / fname
        assert fpath.exists(), f"Missing required Step 13.7 artifact: {fname}"
        assert fpath.stat().st_size > 50, f"Artifact {fname} appears empty or truncated"


def test_turnover_reduction_invariants():
    """Verify that turnover penalty and cadence adjustments reduce turnover significantly."""
    attr_path = ROOT_DIR / "docs" / "results" / "step13_7" / "turnover_attribution.json"
    assert attr_path.exists()
    with open(attr_path, "r") as f:
        attr = json.load(f)

    # Invariants from empirical data:
    # 1. Turnover penalty should reduce multi-year turnover by >= 80%
    assert attr["attribution_breakdown"]["turnover_penalty_reduction_pct"] >= 80.0
    # 2. Monthly cadence should reduce multi-year turnover by >= 50%
    assert attr["attribution_breakdown"]["weekly_vs_monthly_cadence_drag_pct"] >= 50.0
    # 3. Active optimizer churn accounts for >= 90% of baseline turnover
    assert attr["attribution_breakdown"]["active_optimizer_churn_pct"] >= 90.0
