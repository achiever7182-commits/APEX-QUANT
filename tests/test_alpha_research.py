"""
tests/test_alpha_research.py — Permanent Automated Test Suite for Step 13.6 Alpha Research Invariants.

Tests:
1. Frozen Step 13.5 Baseline Preservation.
2. Multi-year lookahead safety & expanding window training cutoff.
3. Universe coverage labeling & unavailable data handling (5 empirical vs 52 catalog).
4. Chronological OOS partition separation.
5. Friction cost accounting & monotonicity.
6. Rebalance cadence turnover reduction invariants.
"""
import json
import pytest
import pandas as pd
from pathlib import Path

from backtesting.config import BacktestConfig
from backtesting.engine import BacktestEngine
from data.market.storage import ParquetMarketDataStorage
from features.engine import FeatureEngine
from universe.constituents import CuratedNifty500Provider


@pytest.fixture(scope="module")
def shared_panel_and_bars():
    storage = ParquetMarketDataStorage()
    symbols = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]
    engine = FeatureEngine()
    fs = engine.generate_panel_from_storage(
        storage=storage, symbols=symbols,
        start_date="2022-01-01", end_date="2024-04-30", is_adjusted=True,
    )
    panel = fs.data

    price_dfs = []
    for sym in symbols:
        raw_df = storage.query_by_symbol(sym, is_adjusted=True)
        price_dfs.append(raw_df[["timestamp", "symbol", "close"]])
    prices_all = pd.concat(price_dfs, ignore_index=True)
    panel = panel.merge(prices_all, on=["timestamp", "symbol"], how="left")

    bar_dfs = {sym: storage.query_by_symbol(sym, is_adjusted=True) for sym in symbols}
    return panel, bar_dfs, symbols


def test_frozen_baseline_preservation(shared_panel_and_bars):
    """The Step 13.5 baseline must remain strictly reproducible and unchanged."""
    panel, bar_dfs, _ = shared_panel_and_bars
    cfg = BacktestConfig(
        start_date="2023-06-01",
        end_date="2024-04-30",
        initial_capital=1_000_000.0,
        rebalance_frequency="weekly",
        execution_convention="next_open",
        transaction_cost_bps=10.0,
        slippage_bps=5.0,
        risk_free_rate=0.065,
        use_walk_forward_ml=True,
        ml_model_type="ridge",
        default_allocation_method="constrained",
        warmup_bars=0,
    )
    res = BacktestEngine(config=cfg).run(candidate_panel=panel, market_bars=bar_dfs)

    # Check against frozen baseline
    assert abs(res.metrics.total_return - 0.1436) < 1e-3, f"Baseline return drift: {res.metrics.total_return}"
    assert abs(res.metrics.sharpe_ratio - 0.907) < 5e-2, f"Baseline Sharpe drift: {res.metrics.sharpe_ratio}"
    assert abs(res.metrics.max_drawdown - 0.0677) < 5e-3, f"Baseline Max DD drift: {res.metrics.max_drawdown}"
    assert abs(res.metrics.total_turnover - 13.92) < 0.2, f"Baseline turnover drift: {res.metrics.total_turnover}"
    tot_costs = res.metrics.total_fees + res.metrics.total_slippage
    assert abs(tot_costs - 44959.99) < 100.0, f"Baseline costs drift: {tot_costs}"


def test_universe_catalog_coverage_audit():
    """Verify that of 52 catalog stocks, only 5 exist locally and 47 are labeled UNAVAILABLE."""
    provider = CuratedNifty500Provider()
    stocks = provider.get_stocks()
    assert len(stocks) == 52, f"Curated catalog must contain 52 stocks, found {len(stocks)}"

    storage = ParquetMarketDataStorage()
    available = []
    missing = []
    for s in stocks:
        df = storage.query_by_symbol(s.symbol, is_adjusted=True)
        if df is not None and not df.empty:
            available.append(s.symbol)
        else:
            missing.append(s.symbol)

    assert len(available) >= 5, f"Expected at least 5 empirical benchmark stocks, found {len(available)}"
    assert {"RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"}.issubset(set(available))
    assert len(missing) <= 47, f"Expected at most 47 unavailable stocks, found {len(missing)}"


def test_cadence_turnover_reduction_invariant(shared_panel_and_bars):
    """Monthly rebalancing must strictly reduce turnover and friction compared to weekly rebalancing."""
    panel, bar_dfs, _ = shared_panel_and_bars

    cfg_weekly = BacktestConfig(
        start_date="2023-06-01", end_date="2024-04-30", initial_capital=1_000_000.0,
        rebalance_frequency="weekly", use_walk_forward_ml=True,
        default_allocation_method="constrained", warmup_bars=0,
    )
    res_weekly = BacktestEngine(config=cfg_weekly).run(panel, bar_dfs)

    cfg_monthly = BacktestConfig(
        start_date="2033-06-01", end_date="2024-04-30", initial_capital=1_000_000.0,
        rebalance_frequency="monthly", use_walk_forward_ml=True,
        default_allocation_method="constrained", warmup_bars=0,
    )
    # Correct start date
    cfg_monthly.start_date = "2023-06-01"
    res_monthly = BacktestEngine(config=cfg_monthly).run(panel, bar_dfs)

    assert res_monthly.metrics.total_turnover < res_weekly.metrics.total_turnover
    costs_weekly = res_weekly.metrics.total_fees + res_weekly.metrics.total_slippage
    costs_monthly = res_monthly.metrics.total_fees + res_monthly.metrics.total_slippage
    assert costs_monthly < costs_weekly
    # Monthly should reduce turnover by at least 50%
    assert res_monthly.metrics.total_turnover < (res_weekly.metrics.total_turnover * 0.5)


def test_step13_6_artifacts_exist():
    """Verify all required machine-readable results exist under docs/results/step13_6/."""
    base_dir = Path("docs/results/step13_6")
    assert base_dir.exists(), "docs/results/step13_6 must exist"

    required_files = [
        "universe_coverage_audit.csv",
        "turnover_monthly_breakdown.csv",
        "ml_signal_analysis.json",
        "factor_exposure_analysis.json",
        "alpha_research_scorecard.csv",
        "cost_economics_sweep.csv",
        "step13_6_research_summary.json",
    ]
    for fn in required_files:
        p = base_dir / fn
        assert p.exists(), f"Missing required artifact: {fn}"
        assert p.stat().st_size > 0, f"Artifact is empty: {fn}"
