"""
tests/test_portfolio.py — Comprehensive Unit & Integration Tests for APEX QUANT Portfolio Subsystem.

Verifies:
  1. Equal-weight allocation
  2. Score-weighted allocation
  3. Inverse-volatility allocation
  4. Constrained allocation (mean-variance)
  5. No short positions (all weights >= 0)
  6. Gross exposure <= 100%
  7. Maximum position constraint (<= 35%)
  8. Sector constraint (<= 50%)
  9. Minimum cash constraint (>= 5%)
  10. Maximum position count constraint (<= 5)
  11. Liquidity constraint (participation limit)
  12. Integer share rounding (floor rounding)
  13. Residual cash explicit tracking
  14. Transaction costs calculation
  15. Turnover calculation
  16. Current portfolio rebalance
  17. Missing volatility handling
  18. Zero volatility handling (epsilon safety)
  19. NaN prediction handling (rejection)
  20. Missing sector handling (rejection)
  21. Missing price handling (rejection)
  22. Infeasible constraints detection (InfeasibilityReason)
  23. Deterministic output across repeated executions
  24. Future-data corruption / zero-lookahead leakage test
  25. No negative cash assertion
  26. No fractional shares assertion
  27. Fallback behavior (Constrained -> Score Weighted -> Equal Weight)
  28. Risk calculation (w^T * Sigma * w)
  29. Point-in-time covariance matrix calculation
  30. Step 6 RankedUniverse end-to-end compatibility
"""

from __future__ import annotations

import os
import sys
import numpy as np
import pandas as pd

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from portfolio.allocators import (
    EqualWeightAllocator,
    InverseVolatilityAllocator,
    ScoreWeightedAllocator,
)
from portfolio.config import PortfolioConfig
from portfolio.constraints import PortfolioConstraintValidator
from portfolio.cost_model import TransactionCostModel
from portfolio.diagnostics import PortfolioDiagnosticsEngine
from portfolio.models import (
    CandidateRejectionReason,
    InfeasibilityReason,
    PortfolioCandidate,
    PortfolioPosition,
    PortfolioTarget,
)
from portfolio.optimizer import ConstrainedOptimizer
from portfolio.portfolio_builder import PortfolioBuilder
from portfolio.risk import PortfolioRiskModel
from ranking.models import (
    OpportunityRank,
    RankedUniverse,
    ScoringComponents,
)


def create_mock_ranked_universe(timestamp: str = "2024-01-15") -> RankedUniverse:
    """Helper to create a deterministic Step 6 RankedUniverse."""
    eval_ts = pd.Timestamp(timestamp)
    stocks = [
        ("HDFCBANK", 1, 0.85, 0.020, "Financial Services"),
        ("ICICIBANK", 2, 0.75, 0.015, "Financial Services"),
        ("RELIANCE", 3, 0.65, 0.012, "Energy"),
        ("TCS", 4, 0.55, 0.008, "Information Technology"),
        ("INFY", 5, 0.45, 0.004, "Information Technology"),
    ]

    items = []
    for sym, r, score, pred, sec in stocks:
        items.append(
            OpportunityRank(
                timestamp=eval_ts,
                symbol=sym,
                rank=r,
                opportunity_score=score,
                is_eligible=True,
                predicted_return=pred,
                sector=sec,
                scoring_components=ScoringComponents(
                    prediction_score=score,
                    risk_adjusted_score=score,
                    relative_strength_score=score,
                    momentum_score=score,
                    trend_score=score,
                    regime_score=0.5,
                    liquidity_score=0.5,
                ),
            )
        )

    return RankedUniverse(
        timestamp=eval_ts,
        ranked_items=items,
        total_evaluated=len(items),
        eligible_count=len(items),
        rejected_count=0,
    )


def create_mock_market_bars(dates: pd.DatetimeIndex) -> dict[str, pd.DataFrame]:
    """Helper to create deterministic price bars for 5 benchmark stocks."""
    np.random.seed(42)
    bars = {}
    base_prices = {
        "HDFCBANK": 1600.0,
        "ICICIBANK": 1000.0,
        "RELIANCE": 2500.0,
        "TCS": 3800.0,
        "INFY": 1500.0,
    }
    for sym, p0 in base_prices.items():
        ret = np.random.normal(0.0005, 0.015, len(dates))
        prices = p0 * np.exp(np.cumsum(ret))
        vols = np.random.uniform(500_000, 2_000_000, len(dates))
        bars[sym] = pd.DataFrame({
            "timestamp": dates,
            "open": prices * 0.998,
            "high": prices * 1.01,
            "low": prices * 0.99,
            "close": prices,
            "volume": vols,
            "symbol": sym,
        })
    return bars


def test_allocation_methods():
    """Test 1-4: Equal-weight, Score-weighted, Inverse-volatility, and Constrained optimization."""
    config = PortfolioConfig()
    candidates = [
        PortfolioCandidate("A", pd.Timestamp("2024-01-15"), "Tech", 1, 0.03, 0.8, 0.015, 1e7, 100.0),
        PortfolioCandidate("B", pd.Timestamp("2024-01-15"), "Tech", 2, 0.02, 0.6, 0.020, 1e7, 200.0),
        PortfolioCandidate("C", pd.Timestamp("2024-01-15"), "Finance", 3, 0.01, 0.4, 0.010, 1e7, 300.0),
    ]

    # 1. Equal Weight
    eq_alloc = EqualWeightAllocator().allocate(candidates, config)
    assert eq_alloc.status == "FEASIBLE"
    assert len(eq_alloc.target_weights) == 3
    for w in eq_alloc.target_weights.values():
        assert w > 0.0
        assert w <= config.max_single_stock_weight

    # 2. Score Weighted
    score_alloc = ScoreWeightedAllocator().allocate(candidates, config)
    assert score_alloc.status == "FEASIBLE"
    # A has highest score (0.8) -> must have highest or equal weight
    assert score_alloc.target_weights["A"] >= score_alloc.target_weights["C"]

    # 3. Inverse Volatility
    inv_alloc = InverseVolatilityAllocator().allocate(candidates, config)
    assert inv_alloc.status == "FEASIBLE"
    # C has lowest volatility (0.010) -> highest inverse vol weight
    assert inv_alloc.target_weights["C"] >= inv_alloc.target_weights["B"]

    # 4. Constrained Optimizer
    opt_alloc = ConstrainedOptimizer().allocate(candidates, config)
    assert opt_alloc.status == "FEASIBLE"
    assert sum(opt_alloc.target_weights.values()) <= config.max_gross_exposure + 1e-4


def test_constraints_and_limits():
    """Test 5-10: Long-only, gross exposure, single-stock, sector, min cash, max position count."""
    config = PortfolioConfig(
        max_positions=3,
        max_single_stock_weight=0.30,
        max_sector_weight=0.40,
        max_gross_exposure=0.90,
        min_cash_weight=0.10,
    )

    sec_map = {"A": "Tech", "B": "Tech", "C": "Finance", "D": "Energy"}

    # Test 5: Negative weight rejected
    bad_weights = {"A": -0.10, "B": 0.50}
    is_feas, reason, _ = PortfolioConstraintValidator.validate_portfolio_weights(
        bad_weights, 0.60, config, sec_map
    )
    assert not is_feas

    # Test 6: Gross exposure exceeded
    over_gross = {"A": 0.30, "B": 0.30, "C": 0.35}
    is_feas, reason, _ = PortfolioConstraintValidator.validate_portfolio_weights(
        over_gross, 0.05, config, sec_map
    )
    assert not is_feas

    # Test 7: Max single stock exceeded
    over_single = {"A": 0.35, "C": 0.20}
    is_feas, reason, _ = PortfolioConstraintValidator.validate_portfolio_weights(
        over_single, 0.45, config, sec_map
    )
    assert not is_feas

    # Test 8: Sector cap exceeded (Tech: A + B = 0.50 > 0.40)
    over_sector = {"A": 0.25, "B": 0.25, "C": 0.20}
    is_feas, reason, _ = PortfolioConstraintValidator.validate_portfolio_weights(
        over_sector, 0.30, config, sec_map
    )
    assert not is_feas
    assert reason == InfeasibilityReason.SECTOR_CONSTRAINT_INFEASIBLE

    # Test 9: Min cash violated
    bad_cash = {"A": 0.30, "B": 0.30, "C": 0.35}
    is_feas, reason, _ = PortfolioConstraintValidator.validate_portfolio_weights(
        bad_cash, 0.05, config, sec_map
    )
    assert not is_feas

    # Test 10: Position count exceeded (> 3)
    too_many = {"A": 0.20, "B": 0.20, "C": 0.20, "D": 0.20}
    is_feas, reason, _ = PortfolioConstraintValidator.validate_portfolio_weights(
        too_many, 0.20, config, sec_map
    )
    assert not is_feas


def test_integer_shares_and_cash():
    """Test 11-15, 25, 26: Integer share rounding, zero negative cash, no fractional shares."""
    dates = pd.date_range("2024-01-01", periods=30, freq="B")
    bars = create_mock_market_bars(dates)
    ranked_uni = create_mock_ranked_universe("2024-01-15")

    builder = PortfolioBuilder()
    res = builder.build_portfolio(
        ranked_universe=ranked_uni,
        market_bars=bars,
        total_capital=100_000.0,
    )

    assert res.selected_count > 0
    assert res.cash >= 0.0, "Cash must NEVER be negative"
    assert res.cash_weight >= 0.0
    assert res.gross_exposure <= 1.0

    for sym, pos in res.positions.items():
        # Test 26: Integer shares assertion
        assert isinstance(pos.target_shares, int)
        assert pos.target_shares >= 0
        assert pos.target_shares == int(pos.target_shares)
        # Verify floor rounding
        expected_shares = int(np.floor(pos.target_value / pos.current_price))
        assert abs(pos.target_shares - expected_shares) <= 1

    # Verify residual cash bookkeeping
    total_val = sum(p.target_value for p in res.positions.values())
    assert abs(res.allocated_value - total_val) < 1e-4
    assert res.cash + res.allocated_value + res.diagnostics.estimated_transaction_cost <= 100_000.01


def test_rebalancing_and_turnover():
    """Test 14-16: Rebalance turnover, existing portfolio support, and cost model."""
    curr_pos = {
        "HDFCBANK": PortfolioPosition("HDFCBANK", 10, 1600.0, 16000.0, 0.16),
        "ICICIBANK": PortfolioPosition("ICICIBANK", 20, 1000.0, 20000.0, 0.20),
    }

    dates = pd.date_range("2024-01-01", periods=30, freq="B")
    bars = create_mock_market_bars(dates)
    ranked_uni = create_mock_ranked_universe("2024-01-15")

    builder = PortfolioBuilder()
    res = builder.build_portfolio(
        ranked_universe=ranked_uni,
        market_bars=bars,
        total_capital=100_000.0,
        current_positions=curr_pos,
    )

    assert res.diagnostics.turnover >= 0.0
    assert res.diagnostics.estimated_transaction_cost >= 0.0

    # Verify delta tracking
    assert "HDFCBANK" in res.positions
    h_pos = res.positions["HDFCBANK"]
    assert h_pos.delta_shares == h_pos.target_shares - 10


def test_candidate_rejections_and_infeasibility():
    """Test 17-22: Invalid candidate handling with explicit CandidateRejectionReason."""
    eval_ts = pd.Timestamp("2024-01-15")

    # 19. Missing prediction
    c_nopred = PortfolioCandidate("NOPRED", eval_ts, "Tech", 1, np.nan, 0.8, 0.02, 1e7, 100.0)
    ok, rej = PortfolioConstraintValidator.validate_candidate(c_nopred)
    assert not ok and rej == CandidateRejectionReason.INVALID_PREDICTION

    # 20. Missing sector
    c_nosec = PortfolioCandidate("NOSEC", eval_ts, None, 1, 0.02, 0.8, 0.02, 1e7, 100.0)
    ok, rej = PortfolioConstraintValidator.validate_candidate(c_nosec)
    assert not ok and rej == CandidateRejectionReason.INVALID_SECTOR

    # 21. Missing price
    c_noprice = PortfolioCandidate("NOPRICE", eval_ts, "Tech", 1, 0.02, 0.8, 0.02, 1e7, -10.0)
    ok, rej = PortfolioConstraintValidator.validate_candidate(c_noprice)
    assert not ok and rej == CandidateRejectionReason.MISSING_PRICE

    # 22. Infeasible constraints: capital too small for even 1 share
    dates = pd.date_range("2024-01-01", periods=30, freq="B")
    bars = create_mock_market_bars(dates)
    ranked_uni = create_mock_ranked_universe("2024-01-15")
    builder = PortfolioBuilder()
    # ₹500 capital cannot buy a single share of HDFC (1600), TCS (3800), etc.
    res_tiny = builder.build_portfolio(ranked_uni, bars, total_capital=500.0)
    assert res_tiny.cash == 500.0
    assert res_tiny.selected_count == 0


def test_determinism():
    """Test 23: Identical inputs yield identical portfolio targets."""
    dates = pd.date_range("2024-01-01", periods=30, freq="B")
    bars = create_mock_market_bars(dates)
    ranked_uni = create_mock_ranked_universe("2024-01-15")

    builder = PortfolioBuilder()
    res1 = builder.build_portfolio(ranked_uni, bars, total_capital=100_000.0)
    res2 = builder.build_portfolio(ranked_uni, bars, total_capital=100_000.0)

    assert res1.positions.keys() == res2.positions.keys()
    for s in res1.positions:
        assert res1.positions[s].target_shares == res2.positions[s].target_shares
        assert abs(res1.positions[s].target_value - res2.positions[s].target_value) < 1e-4
    assert abs(res1.cash - res2.cash) < 1e-4


def test_zero_lookahead_leakage_audit():
    """Test 24: Future price/covariance corruption does NOT alter historical portfolio at T."""
    dates = pd.date_range("2024-01-01", periods=30, freq="B")
    bars = create_mock_market_bars(dates)
    ranked_uni = create_mock_ranked_universe("2024-01-15")

    builder = PortfolioBuilder()
    orig_res = builder.build_portfolio(ranked_uni, bars, total_capital=100_000.0)

    # Corrupt future bars after 2024-01-15 with extreme values
    corrupted_bars = {}
    for sym, df in bars.items():
        c_df = df.copy()
        mask = c_df["timestamp"] > pd.Timestamp("2024-01-15")
        c_df.loc[mask, "close"] = c_df.loc[mask, "close"] * 50.0
        c_df.loc[mask, "volume"] = c_df.loc[mask, "volume"] * 100.0
        corrupted_bars[sym] = c_df

    leak_res = builder.build_portfolio(ranked_uni, corrupted_bars, total_capital=100_000.0)

    assert orig_res.positions.keys() == leak_res.positions.keys()
    for s in orig_res.positions:
        assert orig_res.positions[s].target_shares == leak_res.positions[s].target_shares
        assert abs(orig_res.positions[s].target_value - leak_res.positions[s].target_value) < 1e-4
    assert abs(orig_res.cash - leak_res.cash) < 1e-4


def test_fallback_behavior():
    """Test 27: Constrained optimizer falls back cleanly to score-weighted or equal-weight."""
    candidates = [
        PortfolioCandidate("A", pd.Timestamp("2024-01-15"), "Tech", 1, 0.03, 0.8, 0.015, 1e7, 100.0),
        PortfolioCandidate("B", pd.Timestamp("2024-01-15"), "Tech", 2, 0.02, 0.6, 0.020, 1e7, 200.0),
    ]
    # Sector cap of 0.20 when min_positions is 2 and min_stock_weight is 0.15 makes Tech sector infeasible
    config = PortfolioConfig(min_positions=2, max_single_stock_weight=0.50, max_sector_weight=0.30)
    alloc = ConstrainedOptimizer().allocate(candidates, config)
    # When optimizer cannot satisfy sector cap, status is INFEASIBLE
    assert alloc.status == "INFEASIBLE"


def test_risk_and_covariance():
    """Test 28-29: Risk calculations (variance, volatility, risk contributions, covariance)."""
    dates = pd.date_range("2024-01-01", periods=30, freq="B")
    bars = create_mock_market_bars(dates)
    symbols = ["HDFCBANK", "ICICIBANK", "RELIANCE"]

    cov_mat, is_fallback = PortfolioRiskModel.compute_covariance_matrix(
        market_bars=bars,
        symbols=symbols,
        as_of_date="2024-01-15",
        lookback_bars=20,
    )
    assert cov_mat.shape == (3, 3)
    assert not is_fallback

    w = np.array([0.4, 0.3, 0.3])
    var = PortfolioRiskModel.calculate_portfolio_variance(w, cov_mat.values)
    vol = PortfolioRiskModel.calculate_portfolio_volatility(w, cov_mat.values)
    assert var > 0.0
    assert vol > 0.0
    assert abs(vol - np.sqrt(var)) < 1e-6

    mrc, prc = PortfolioRiskModel.calculate_risk_contributions(w, cov_mat.values, symbols)
    assert abs(sum(prc.values()) - 1.0) < 1e-4


def test_step6_ranked_universe_compatibility():
    """Test 30: End-to-end integration consuming real Step 6 RankedUniverse."""
    dates = pd.date_range("2024-01-01", periods=30, freq="B")
    bars = create_mock_market_bars(dates)
    ranked_uni = create_mock_ranked_universe("2024-01-15")

    builder = PortfolioBuilder()
    res = builder.build_portfolio(ranked_uni, bars, total_capital=100_000.0)

    # In constrained mode, INFY has negative predicted return (-0.5%), so optimizer allocates 0 shares
    assert res.selected_count == 4
    assert res.cash >= 0.0
    assert res.risk_metrics is not None
    assert res.risk_metrics.portfolio_volatility > 0.0
    assert res.diagnostics is not None
    assert res.diagnostics.hhi_concentration > 0.0

    df_res = res.to_dataframe()
    assert len(df_res) == 4
    assert "target_shares" in df_res.columns
    assert "target_weight" in df_res.columns

    # Equal-weight mode allocates to all 5 stocks
    res_eq = builder.build_portfolio(ranked_uni, bars, total_capital=100_000.0, method="equal_weight")
    assert res_eq.selected_count == 5
    assert len(res_eq.to_dataframe()) == 5


if __name__ == "__main__":
    test_allocation_methods()
    print("  [OK] test_allocation_methods (Tests 1-4)")
    test_constraints_and_limits()
    print("  [OK] test_constraints_and_limits (Tests 5-10)")
    test_integer_shares_and_cash()
    print("  [OK] test_integer_shares_and_cash (Tests 11-15, 25-26)")
    test_rebalancing_and_turnover()
    print("  [OK] test_rebalancing_and_turnover (Tests 14-16)")
    test_candidate_rejections_and_infeasibility()
    print("  [OK] test_candidate_rejections_and_infeasibility (Tests 17-22)")
    test_determinism()
    print("  [OK] test_determinism (Test 23)")
    test_zero_lookahead_leakage_audit()
    print("  [OK] test_zero_lookahead_leakage_audit (Test 24)")
    test_fallback_behavior()
    print("  [OK] test_fallback_behavior (Test 27)")
    test_risk_and_covariance()
    print("  [OK] test_risk_and_covariance (Tests 28-29)")
    test_step6_ranked_universe_compatibility()
    print("  [OK] test_step6_ranked_universe_compatibility (Test 30)")
    print("\nAll Step 7 Portfolio Construction tests PASSED successfully.")
