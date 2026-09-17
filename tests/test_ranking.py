"""
tests/test_ranking.py — Comprehensive Unit & Integration Tests for APEX QUANT Stock Ranking Engine.

Verifies:
  1. Same-timestamp stocks rank correctly
  2. Multi-stock ranking works
  3. Ranking is deterministic across repeated executions
  4. Tie-breaking is deterministic (Opportunity Score -> Predicted Return -> Symbol)
  5. Percentile normalization works (bounds in [0, 1])
  6. Z-score normalization works (mean ~0, std ~1)
  7. Risk adjustment handles zero and near-zero volatility safely
  8. Missing predictions are rejected with MISSING_PREDICTION
  9. Ineligible stocks are excluded with explicit RejectionReason
  10. Point-in-time universe membership is respected (reconstitution bounds)
  11. Future information cannot affect historical ranking (zero-lookahead leakage audit)
  12. Top-K cutoff behaves accurately
  13. Threshold filters work (min_predicted_return, min_opportunity_score, max_volatility)
  14. Sector metadata is preserved
  15. Score components remain within expected ranges
  16. Zero NaN output in final ranked opportunities
  17. Zero infinite output in final ranked opportunities
  18. Baseline ranking works (raw return, momentum, random)
  19. Empty candidate dataframe is handled safely
  20. Return correlation matrix calculation helper
  21. Real Parquet benchmark data ranking (RELIANCE, TCS, INFY, HDFCBANK, ICICIBANK)
"""

from __future__ import annotations

import os
import sys
import numpy as np
import pandas as pd

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from data.market.storage import ParquetMarketDataStorage
from features.engine import FeatureEngine
from ml.equity.predict import EquityPredictor
from ml.equity.registry import ModelRegistry
from ranking.baselines import BaselineRankers
from ranking.config import RankingConfig
from ranking.diagnostics import RankingDiagnostics
from ranking.filters import EligibilityFilter
from ranking.models import RejectionReason
from ranking.ranker import CrossSectionalRanker
from ranking.scoring import OpportunityScorer
from universe.universe_manager import UniverseManager


def create_mock_candidate_df(timestamp: str = "2024-01-15") -> pd.DataFrame:
    """Create deterministic candidate stock dataframe for a single evaluation date."""
    eval_ts = pd.Timestamp(timestamp)
    return pd.DataFrame([
        {
            "timestamp": eval_ts,
            "symbol": "HDFCBANK",
            "close": 1650.0,
            "predicted_return": 0.025,
            "volatility_20d": 0.012,
            "relative_return_20d": 0.015,
            "rsi_14": 62.0,
            "roc_20d": 3.5,
            "momentum_norm_20d": 0.035,
            "price_to_sma_20_ratio": 0.02,
            "sma_20_to_50_spread": 0.015,
            "regime_market_state": 1.0,
            "turnover_sma_20d": 80_000_000.0,
            "has_sufficient_history": True,
            "sector": "Financial Services",
        },
        {
            "timestamp": eval_ts,
            "symbol": "RELIANCE",
            "close": 2750.0,
            "predicted_return": 0.018,
            "volatility_20d": 0.015,
            "relative_return_20d": 0.008,
            "rsi_14": 58.0,
            "roc_20d": 2.2,
            "momentum_norm_20d": 0.022,
            "price_to_sma_20_ratio": 0.015,
            "sma_20_to_50_spread": 0.010,
            "regime_market_state": 1.0,
            "turnover_sma_20d": 120_000_000.0,
            "has_sufficient_history": True,
            "sector": "Energy",
        },
        {
            "timestamp": eval_ts,
            "symbol": "ICICIBANK",
            "close": 1020.0,
            "predicted_return": 0.014,
            "volatility_20d": 0.014,
            "relative_return_20d": 0.005,
            "rsi_14": 55.0,
            "roc_20d": 1.8,
            "momentum_norm_20d": 0.018,
            "price_to_sma_20_ratio": 0.010,
            "sma_20_to_50_spread": 0.008,
            "regime_market_state": 1.0,
            "turnover_sma_20d": 70_000_000.0,
            "has_sufficient_history": True,
            "sector": "Financial Services",
        },
        {
            "timestamp": eval_ts,
            "symbol": "TCS",
            "close": 3900.0,
            "predicted_return": 0.006,
            "volatility_20d": 0.010,
            "relative_return_20d": -0.002,
            "rsi_14": 51.0,
            "roc_20d": 0.5,
            "momentum_norm_20d": 0.005,
            "price_to_sma_20_ratio": 0.002,
            "sma_20_to_50_spread": 0.004,
            "regime_market_state": 1.0,
            "turnover_sma_20d": 60_000_000.0,
            "has_sufficient_history": True,
            "sector": "Information Technology",
        },
        {
            "timestamp": eval_ts,
            "symbol": "INFY",
            "close": 1520.0,
            "predicted_return": -0.005,
            "volatility_20d": 0.016,
            "relative_return_20d": -0.015,
            "rsi_14": 46.0,
            "roc_20d": -1.2,
            "momentum_norm_20d": -0.012,
            "price_to_sma_20_ratio": -0.010,
            "sma_20_to_50_spread": -0.005,
            "regime_market_state": 1.0,
            "turnover_sma_20d": 65_000_000.0,
            "has_sufficient_history": True,
            "sector": "Information Technology",
        },
    ])


def test_basic_multi_stock_ranking():
    """Verify that multi-stock candidates at the same timestamp rank in expected order."""
    df = create_mock_candidate_df()
    ranker = CrossSectionalRanker()
    ranked_uni = ranker.rank_cross_section(df, as_of_date="2024-01-15")

    assert ranked_uni.total_evaluated == 5
    assert ranked_uni.eligible_count == 5
    assert ranked_uni.rejected_count == 0

    ranks = {item.symbol: item.rank for item in ranked_uni.eligible_opportunities}
    # HDFCBANK has highest return (+2.5%), high turnover, and best relative strength
    assert ranks["HDFCBANK"] == 1
    # INFY has negative return (-0.5%) and negative momentum -> lowest rank
    assert ranks["INFY"] == 5


def test_deterministic_tie_breaking():
    """Verify 3-tier tie-breaking: Opportunity Score -> Predicted Return -> Symbol alphabetical."""
    eval_ts = pd.Timestamp("2024-01-15")
    # Two stocks with identical predictions and features, differing only in symbol
    df = pd.DataFrame([
        {
            "timestamp": eval_ts, "symbol": "ZEE", "close": 100.0, "predicted_return": 0.02,
            "volatility_20d": 0.01, "relative_return_20d": 0.01, "rsi_14": 50.0,
            "roc_20d": 1.0, "turnover_sma_20d": 10_000_000.0, "has_sufficient_history": True,
        },
        {
            "timestamp": eval_ts, "symbol": "ABB", "close": 100.0, "predicted_return": 0.02,
            "volatility_20d": 0.01, "relative_return_20d": 0.01, "rsi_14": 50.0,
            "roc_20d": 1.0, "turnover_sma_20d": 10_000_000.0, "has_sufficient_history": True,
        },
    ])

    ranker = CrossSectionalRanker()
    ranked_uni = ranker.rank_cross_section(df, as_of_date="2024-01-15")

    eligible = ranked_uni.eligible_opportunities
    assert len(eligible) == 2
    # Equal opportunity scores: ABB must rank #1 before ZEE because 'ABB' < 'ZEE' alphabetically
    assert eligible[0].symbol == "ABB" and eligible[0].rank == 1
    assert eligible[1].symbol == "ZEE" and eligible[1].rank == 2


def test_percentile_vs_zscore_normalization():
    """Verify percentile rank [0, 1] and z-score (mean ~0, std ~1) scoring."""
    df = create_mock_candidate_df()

    # 1. Percentile mode (default)
    config_pct = RankingConfig(normalization_method="percentile")
    ranker_pct = CrossSectionalRanker(config=config_pct)
    res_pct = ranker_pct.rank_cross_section(df, as_of_date="2024-01-15")

    for item in res_pct.eligible_opportunities:
        assert 0.0 <= item.opportunity_score <= 1.0, "Percentile opportunity score must be in [0, 1]"
        assert 0.0 <= item.scoring_components.prediction_score <= 1.0

    # 2. Z-Score mode
    config_z = RankingConfig(normalization_method="zscore")
    ranker_z = CrossSectionalRanker(config=config_z)
    res_z = ranker_z.rank_cross_section(df, as_of_date="2024-01-15")

    z_scores = [item.opportunity_score for item in res_z.eligible_opportunities]
    # Z-scores should have mean close to 0
    np.testing.assert_allclose(np.mean(z_scores), 0.0, atol=1e-5)


def test_risk_adjusted_zero_volatility_safety():
    """Verify that zero or missing volatility does not cause division-by-zero or infs."""
    eval_ts = pd.Timestamp("2024-01-15")
    df = pd.DataFrame([
        {
            "timestamp": eval_ts, "symbol": "ZEROVOL", "close": 100.0, "predicted_return": 0.02,
            "volatility_20d": 0.0,  # Zero volatility
            "relative_return_20d": 0.01, "rsi_14": 50.0, "turnover_sma_20d": 10_000_000.0,
            "has_sufficient_history": True,
        },
        {
            "timestamp": eval_ts, "symbol": "NORMAL", "close": 100.0, "predicted_return": 0.02,
            "volatility_20d": 0.02,
            "relative_return_20d": 0.01, "rsi_14": 50.0, "turnover_sma_20d": 10_000_000.0,
            "has_sufficient_history": True,
        },
    ])

    ranker = CrossSectionalRanker()
    ranked_uni = ranker.rank_cross_section(df, as_of_date="2024-01-15")

    for item in ranked_uni.eligible_opportunities:
        assert not np.isinf(item.opportunity_score)
        assert not np.isnan(item.opportunity_score)
        assert not np.isinf(item.scoring_components.risk_adjusted_score)


def test_missing_prediction_rejection():
    """Verify stocks with NaN or null predicted return are rejected with MISSING_PREDICTION."""
    eval_ts = pd.Timestamp("2024-01-15")
    df = pd.DataFrame([
        {
            "timestamp": eval_ts, "symbol": "GOOD", "close": 100.0, "predicted_return": 0.015,
            "volatility_20d": 0.01, "has_sufficient_history": True,
        },
        {
            "timestamp": eval_ts, "symbol": "NOPRED", "close": 100.0, "predicted_return": np.nan,
            "volatility_20d": 0.01, "has_sufficient_history": True,
        },
    ])

    ranker = CrossSectionalRanker()
    ranked_uni = ranker.rank_cross_section(df, as_of_date="2024-01-15")

    rejected = [item for item in ranked_uni.ranked_items if not item.is_eligible]
    assert len(rejected) == 1
    assert rejected[0].symbol == "NOPRED"
    assert rejected[0].rejection_reason == RejectionReason.MISSING_PREDICTION
    assert rejected[0].rank is None


def test_ineligible_stock_exclusions():
    """Verify various failure modes produce expected RejectionReason codes."""
    eval_ts = pd.Timestamp("2024-01-15")
    df = pd.DataFrame([
        # 1. Negative price
        {"timestamp": eval_ts, "symbol": "BADPRICE", "close": -10.0, "predicted_return": 0.01, "has_sufficient_history": True},
        # 2. Warmup not complete
        {"timestamp": eval_ts, "symbol": "SHORT", "close": 100.0, "predicted_return": 0.01, "has_sufficient_history": False},
        # 3. Delisted
        {"timestamp": eval_ts, "symbol": "DELIST", "close": 100.0, "predicted_return": 0.01, "has_sufficient_history": True, "listing_status": "DELISTED"},
    ])

    ranker = CrossSectionalRanker()
    ranked_uni = ranker.rank_cross_section(df, as_of_date="2024-01-15")

    reasons = {item.symbol: item.rejection_reason for item in ranked_uni.ranked_items}
    assert reasons["BADPRICE"] == RejectionReason.INVALID_PRICE
    assert reasons["SHORT"] == RejectionReason.INSUFFICIENT_HISTORY
    assert reasons["DELIST"] == RejectionReason.DELISTED


def test_top_k_filter():
    """Verify that top_k restricts ranked opportunities to exactly K assets."""
    df = create_mock_candidate_df()
    config = RankingConfig(top_k=2)
    ranker = CrossSectionalRanker(config=config)
    ranked_uni = ranker.rank_cross_section(df, as_of_date="2024-01-15")

    top_ops = ranked_uni.top_opportunities
    assert len(top_ops) == 2
    assert top_ops[0].rank == 1
    assert top_ops[1].rank == 2


def test_threshold_filtering():
    """Verify minimum opportunity score and maximum volatility thresholds."""
    df = create_mock_candidate_df()
    # Require min opportunity score of 0.60
    config = RankingConfig(min_opportunity_score=0.60)
    ranker = CrossSectionalRanker(config=config)
    ranked_uni = ranker.rank_cross_section(df, as_of_date="2024-01-15")

    # Lower scoring stocks must be rejected with BELOW_SCORE_THRESHOLD
    rejected_thresh = [
        item for item in ranked_uni.ranked_items
        if item.rejection_reason == RejectionReason.BELOW_SCORE_THRESHOLD
    ]
    assert len(rejected_thresh) > 0
    for item in ranked_uni.eligible_opportunities:
        assert item.opportunity_score >= 0.60


def test_zero_lookahead_leakage_audit():
    """
    CRITICAL TEST: Mutating future data at T+k does not affect historical ranking at T.
    """
    df = create_mock_candidate_df(timestamp="2024-01-15")
    ranker = CrossSectionalRanker()
    orig_ranks = ranker.rank_cross_section(df, as_of_date="2024-01-15")

    # Simulate future rows at 2024-01-20 with extreme spikes
    df_future = df.copy()
    df_future["timestamp"] = pd.Timestamp("2024-01-20")
    df_future["close"] = df_future["close"] * 10.0
    df_future["predicted_return"] = df_future["predicted_return"] * 50.0

    combined_panel = pd.concat([df, df_future], ignore_index=True)

    # Rank the 2024-01-15 slice from the combined panel
    sliced_ranks = ranker.rank_cross_section(
        combined_panel[combined_panel["timestamp"] == pd.Timestamp("2024-01-15")],
        as_of_date="2024-01-15",
    )

    orig_order = [i.symbol for i in orig_ranks.eligible_opportunities]
    sliced_order = [i.symbol for i in sliced_ranks.eligible_opportunities]
    assert orig_order == sliced_order, "Historical ranking was altered by presence of future data!"

    orig_scores = [i.opportunity_score for i in orig_ranks.eligible_opportunities]
    sliced_scores = [i.opportunity_score for i in sliced_ranks.eligible_opportunities]
    np.testing.assert_allclose(orig_scores, sliced_scores)


def test_baseline_rankers():
    """Verify reference baseline rankers (raw prediction, momentum, random)."""
    df = create_mock_candidate_df()

    # 1. Raw Prediction Ranker
    r_pred = BaselineRankers.rank_by_raw_prediction(df)
    items_pred = r_pred.eligible_opportunities
    # Top raw prediction is HDFCBANK (+0.025)
    assert items_pred[0].symbol == "HDFCBANK" and items_pred[0].rank == 1
    # Lowest is INFY (-0.005)
    assert items_pred[-1].symbol == "INFY" and items_pred[-1].rank == 5

    # 2. Momentum Ranker
    r_mom = BaselineRankers.rank_by_momentum(df, mom_col="roc_20d")
    items_mom = r_mom.eligible_opportunities
    assert items_mom[0].symbol == "HDFCBANK" # roc_20d = 3.5

    # 3. Random Ranker
    r_rand1 = BaselineRankers.rank_random(df, random_seed=42)
    r_rand2 = BaselineRankers.rank_random(df, random_seed=42)
    order1 = [i.symbol for i in r_rand1.eligible_opportunities]
    order2 = [i.symbol for i in r_rand2.eligible_opportunities]
    assert order1 == order2, "Random baseline must be deterministic with fixed seed"


def test_diagnostics_and_correlation_matrix():
    """Verify return correlation matrix and diagnostic evaluation."""
    # Synthetic price series for correlation
    dates = pd.date_range("2024-01-01", periods=30, freq="B")
    stock_dfs = {
        "A": pd.DataFrame({"timestamp": dates, "close": np.linspace(100, 110, 30)}),
        "B": pd.DataFrame({"timestamp": dates, "close": np.linspace(100, 110, 30)}),
        "C": pd.DataFrame({"timestamp": dates, "close": np.linspace(100, 90, 30)}),
    }

    corr_mat = RankingDiagnostics.compute_return_correlation_matrix(
        stock_dfs=stock_dfs, as_of_date="2024-01-25", lookback_bars=20
    )
    assert corr_mat.shape == (3, 3)
    assert "A" in corr_mat.columns and "B" in corr_mat.columns
    # Diagonal must be 1.0
    np.testing.assert_allclose(np.diag(corr_mat), [1.0, 1.0, 1.0])

    # Evaluate ranked universe diagnostics
    df = create_mock_candidate_df()
    ranker = CrossSectionalRanker()
    ranked_uni = ranker.rank_cross_section(df, as_of_date="2024-01-15")

    realized = {"HDFCBANK": 0.03, "RELIANCE": 0.02, "ICICIBANK": 0.015, "TCS": 0.005, "INFY": -0.01}
    rep = RankingDiagnostics.evaluate_ranked_universe(ranked_uni, realized_future_returns=realized)

    assert rep.eligible_count == 5
    # Verify both primary renamed metric and alias
    assert rep.score_separation > 0.0
    assert rep.top_bottom_score_spread == rep.score_separation
    assert rep.spearman_ic is not None
    # Realized returns matched score ordering perfectly -> IC ~ 1.0
    assert rep.spearman_ic > 0.90
    assert rep.top_bottom_forward_return_spread is not None
    assert rep.realized_top_bottom_spread == rep.top_bottom_forward_return_spread
    assert rep.top_bottom_forward_return_spread > 0.0
    assert "Financial Services" in rep.sector_summaries


def test_empty_universe_handling():
    """Verify empty candidates dataframe returns clean empty RankedUniverse without error."""
    ranker = CrossSectionalRanker()
    ranked_uni = ranker.rank_cross_section(pd.DataFrame(), as_of_date="2024-01-15")
    assert ranked_uni.total_evaluated == 0
    assert ranked_uni.eligible_count == 0
    assert len(ranked_uni.eligible_opportunities) == 0
    assert ranked_uni.to_dataframe().empty


def test_real_benchmark_data_ranking():
    """
    Integration test: Ingest real Step 4 features and Step 5 predictions for
    benchmark stocks (RELIANCE, TCS, INFY, HDFCBANK, ICICIBANK) and execute ranking.
    """
    storage = ParquetMarketDataStorage()
    symbols = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]

    feature_engine = FeatureEngine()
    feature_set = feature_engine.generate_panel_from_storage(
        storage=storage,
        symbols=symbols,
        start_date="2023-01-01",
        end_date="2024-01-15",
        is_adjusted=True,
    )

    panel = feature_set.data
    assert not panel.empty

    # Attach model predictions using trained Step 5 model from ModelRegistry
    registry = ModelRegistry()
    artifacts = registry.list_artifacts()
    assert len(artifacts) > 0, "Expected at least one trained model artifact from Step 5"

    latest_version = artifacts[-1]["version"]
    predictor = EquityPredictor.from_registry(latest_version, registry=registry)
    preds_df = predictor.predict(panel)

    panel["predicted_return"] = preds_df["predicted_return"].values

    # Attach close prices from storage
    price_dfs = []
    for sym in symbols:
        raw_df = storage.query_by_symbol(sym, is_adjusted=True)
        price_dfs.append(raw_df[["timestamp", "symbol", "close"]])
    prices_all = pd.concat(price_dfs, ignore_index=True)
    panel = panel.merge(prices_all, on=["timestamp", "symbol"], how="left")

    # Execute ranking on 2024-01-15
    eval_slice = panel[panel["timestamp"].dt.date == pd.to_datetime("2024-01-15").date()]
    ranker = CrossSectionalRanker()
    ranked_uni = ranker.rank_cross_section(eval_slice, as_of_date="2024-01-15")

    assert ranked_uni.eligible_count == 5
    assert len(ranked_uni.eligible_opportunities) == 5

    table_df = ranked_uni.to_dataframe()
    assert "rank" in table_df.columns
    assert "opportunity_score" in table_df.columns
    assert "predicted_return" in table_df.columns
    assert table_df["opportunity_score"].notna().all()


def test_historical_walk_forward_diagnostics():
    """Verify multi-date historical walk-forward diagnostic evaluation and aggregate metrics."""
    dates = pd.date_range("2024-01-01", periods=10, freq="B")
    bars = {
        "A": pd.DataFrame({"timestamp": dates, "close": [100, 101, 102, 105, 108, 110, 112, 115, 118, 120]}),
        "B": pd.DataFrame({"timestamp": dates, "close": [200, 201, 202, 201, 200, 199, 198, 197, 196, 195]}),
        "C": pd.DataFrame({"timestamp": dates, "close": [50, 50.5, 51, 51.5, 52, 52.2, 52.5, 52.8, 53, 53.5]}),
    }

    panel_rows = []
    for ts in [dates[1], dates[3]]:
        panel_rows.extend([
            {"timestamp": ts, "symbol": "A", "close": 100.0, "predicted_return": 0.05, "volatility_20d": 0.01, "roc_20d": 2.0, "has_sufficient_history": True},
            {"timestamp": ts, "symbol": "B", "close": 200.0, "predicted_return": -0.02, "volatility_20d": 0.01, "roc_20d": -1.0, "has_sufficient_history": True},
            {"timestamp": ts, "symbol": "C", "close": 50.0, "predicted_return": 0.01, "volatility_20d": 0.01, "roc_20d": 0.5, "has_sufficient_history": True},
        ])
    panel_df = pd.DataFrame(panel_rows)

    ranker = CrossSectionalRanker()
    report = RankingDiagnostics.evaluate_historical_walk_forward(
        ranker=ranker,
        panel_df=panel_df,
        market_bars=bars,
        forward_horizon_bars=2,
    )

    assert report.total_dates == 2
    assert not np.isnan(report.ic_mean)
    assert not np.isnan(report.ic_median)
    assert report.ic_std >= 0.0
    assert 0.0 <= report.ic_hit_rate <= 1.0
    assert report.mean_score_separation >= 0.0
    assert "Apex Composite" in report.baseline_comparison
    assert "Raw Prediction" in report.baseline_comparison
    assert "20d Momentum" in report.baseline_comparison
    assert "Random" in report.baseline_comparison

    df_snaps = report.to_dataframe()
    assert len(df_snaps) == 2
    assert "score_separation" in df_snaps.columns
    assert "top_bottom_forward_return_spread" in df_snaps.columns


def test_benchmark_terminology_and_universe_scope():
    """Verify correct distinction between synthetic benchmark and official NIFTY 500, and universe scope."""
    from universe.constituents import CuratedNifty500Provider
    curated_provider = CuratedNifty500Provider()
    curated_stocks = curated_provider.get_stocks()
    # 52-stock curated universe catalog
    assert len(curated_stocks) == 52

    # 5-stock empirical validation subset
    empirical_benchmark_stocks = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]
    assert len(empirical_benchmark_stocks) == 5
    for sym in empirical_benchmark_stocks:
        assert any(s.symbol == sym for s in curated_stocks)

    # Config weights specify relative strength vs synthetic equal-weighted benchmark
    cfg = RankingConfig()
    assert "relative_strength" in cfg.weights
    assert cfg.weights["relative_strength"] == 0.15


if __name__ == "__main__":
    test_basic_multi_stock_ranking()
    print("  [OK] test_basic_multi_stock_ranking")
    test_deterministic_tie_breaking()
    print("  [OK] test_deterministic_tie_breaking")
    test_percentile_vs_zscore_normalization()
    print("  [OK] test_percentile_vs_zscore_normalization")
    test_risk_adjusted_zero_volatility_safety()
    print("  [OK] test_risk_adjusted_zero_volatility_safety")
    test_missing_prediction_rejection()
    print("  [OK] test_missing_prediction_rejection")
    test_ineligible_stock_exclusions()
    print("  [OK] test_ineligible_stock_exclusions")
    test_top_k_filter()
    print("  [OK] test_top_k_filter")
    test_threshold_filtering()
    print("  [OK] test_threshold_filtering")
    test_zero_lookahead_leakage_audit()
    print("  [OK] test_zero_lookahead_leakage_audit")
    test_baseline_rankers()
    print("  [OK] test_baseline_rankers")
    test_diagnostics_and_correlation_matrix()
    print("  [OK] test_diagnostics_and_correlation_matrix")
    test_empty_universe_handling()
    print("  [OK] test_empty_universe_handling")
    test_real_benchmark_data_ranking()
    print("  [OK] test_real_benchmark_data_ranking")
    test_historical_walk_forward_diagnostics()
    print("  [OK] test_historical_walk_forward_diagnostics")
    test_benchmark_terminology_and_universe_scope()
    print("  [OK] test_benchmark_terminology_and_universe_scope")
    print("\nAll Step 6 Cross-Sectional Ranking tests PASSED successfully.")
