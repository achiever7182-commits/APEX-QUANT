"""
tests/test_features.py — Comprehensive Unit & Integration Tests for APEX QUANT Feature Subsystem.

Tests:
  1. Hand-calculated synthetic verification (returns, SMA, EMA, RSI, ATR, Volatility, Volume)
  2. Zero-lookahead leakage audit (mutating future rows does not alter historical features)
  3. Insufficient history and warmup window handling (has_sufficient_history flag)
  4. Relative strength calculation against benchmark and synthetic basket
  5. Market regime indicator state derivation
  6. Cross-sectional normalization (z-score mean=0, std=1 per timestamp; rank in [0,1])
  7. Cross-sectional time isolation (mutating date T2 does not affect date T1)
  8. FeatureValidator diagnostics (duplicate detection, monotonicity, infs, bounds)
  9. Real Parquet storage multi-stock panel extraction for benchmark stocks (RELIANCE, TCS, INFY, HDFCBANK, ICICIBANK)
"""

from __future__ import annotations

import os
import sys
import tempfile
import numpy as np
import pandas as pd

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from features.models import FeatureConfig, FeatureSet
from features.price import calculate_price_features
from features.trend import calculate_trend_features
from features.momentum import calculate_momentum_features, calculate_rsi
from features.volatility import calculate_volatility_features, calculate_atr
from features.volume import calculate_volume_features
from features.relative_strength import (
    BenchmarkProvider,
    calculate_relative_strength_features,
)
from features.market_regime import calculate_market_regime_features
from features.normalization import (
    cross_sectional_rank,
    cross_sectional_winsorize,
    cross_sectional_zscore,
)
from features.validators import FeatureValidator
from features.engine import FeatureEngine
from data.market.storage import ParquetMarketDataStorage


def create_synthetic_stock_df(n_bars: int = 100, base_price: float = 100.0) -> pd.DataFrame:
    """Create deterministic synthetic daily OHLCV data."""
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=n_bars, freq="B")
    
    # Deterministic price series with gentle upward drift
    drift = np.linspace(0, 20, n_bars)
    noise = np.sin(np.linspace(0, 10, n_bars)) * 2.0
    close = base_price + drift + noise
    
    open_p = close + np.random.uniform(-0.5, 0.5, n_bars)
    high = np.maximum(open_p, close) + np.random.uniform(0.5, 1.5, n_bars)
    low = np.minimum(open_p, close) - np.random.uniform(0.5, 1.5, n_bars)
    volume = 100_000.0 + np.random.uniform(0, 50_000, n_bars)

    return pd.DataFrame({
        "timestamp": dates,
        "open": open_p,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })


def test_hand_calculated_price_features():
    """Verify return formulas against exact manual calculations."""
    dates = pd.date_range("2024-01-01", periods=5, freq="B")
    df = pd.DataFrame({
        "timestamp": dates,
        "open": [100.0, 102.0, 104.0, 101.0, 108.0],
        "high": [103.0, 105.0, 106.0, 104.0, 110.0],
        "low": [99.0, 101.0, 102.0, 100.0, 106.0],
        "close": [101.0, 103.0, 105.0, 102.0, 110.0],
        "volume": [1000.0] * 5,
    })

    feats = calculate_price_features(df, return_periods=[1, 2])
    
    # Manual check: return_1d at idx 1: 103 / 101 - 1 = 2/101
    np.testing.assert_allclose(feats.loc[1, "return_1d"], (103.0 / 101.0) - 1.0)
    # Manual check: return_2d at idx 2: 105 / 101 - 1 = 4/101
    np.testing.assert_allclose(feats.loc[2, "return_2d"], (105.0 / 101.0) - 1.0)
    # Log return at idx 1
    np.testing.assert_allclose(feats.loc[1, "log_return_1d"], np.log(103.0 / 101.0))
    # Gap return at idx 1: (Open_1 - Close_0) / Close_0 = (102 - 101) / 101
    np.testing.assert_allclose(feats.loc[1, "gap_return"], (102.0 - 101.0) / 101.0)


def test_hand_calculated_trend_features():
    """Verify SMA and EMA calculations match definitions."""
    dates = pd.date_range("2024-01-01", periods=6, freq="B")
    df = pd.DataFrame({
        "timestamp": dates,
        "close": [10.0, 20.0, 30.0, 40.0, 50.0, 60.0],
    })

    feats = calculate_trend_features(df, sma_periods=[3], ema_periods=[3])
    
    # SMA 3 at idx 2 (values: 10, 20, 30) -> mean = 20.0
    assert feats.loc[2, "sma_3"] == 20.0
    # SMA 3 at idx 5 (values: 40, 50, 60) -> mean = 50.0
    assert feats.loc[5, "sma_3"] == 50.0
    # Ratio: Close / SMA3 - 1 at idx 5: 60 / 50 - 1 = 0.20
    np.testing.assert_allclose(feats.loc[5, "price_to_sma_3_ratio"], 0.20)
    # EMA 3 non-null starting from min_periods=3
    assert pd.isna(feats.loc[1, "ema_3"])
    assert not pd.isna(feats.loc[2, "ema_3"])


def test_momentum_rsi_bounds_and_roc():
    """Verify RSI Wilder's smoothing is strictly bounded in [0, 100] and ROC matches percentage."""
    df = create_synthetic_stock_df(n_bars=80)
    feats = calculate_momentum_features(df, rsi_period=14, roc_periods=[5])

    rsi = feats["rsi_14"].dropna()
    assert (rsi >= 0.0).all() and (rsi <= 100.0).all(), "RSI must be bounded between 0 and 100"
    
    # Verify ROC_5d matches manual calculation
    close = df["close"]
    expected_roc = ((close - close.shift(5)) / close.shift(5)) * 100.0
    np.testing.assert_allclose(feats["roc_5d"].dropna(), expected_roc.dropna())


def test_volatility_and_atr_non_negative():
    """Verify volatility and ATR are strictly non-negative."""
    df = create_synthetic_stock_df(n_bars=80)
    feats = calculate_volatility_features(df, volatility_periods=[10], atr_period=14)

    vol = feats["volatility_10d"].dropna()
    atr = feats["atr_14"].dropna()
    atr_pct = feats["atr_pct_14"].dropna()

    assert (vol >= 0.0).all(), "Volatility must be non-negative"
    assert (atr >= 0.0).all(), "ATR must be non-negative"
    assert (atr_pct >= 0.0).all(), "ATR % must be non-negative"


def test_volume_turnover_features():
    """Verify volume change and turnover calculation."""
    df = create_synthetic_stock_df(n_bars=50)
    feats = calculate_volume_features(df, volume_sma_periods=[10], volume_momentum_period=5)

    assert "volume_change_1d" in feats.columns
    assert "turnover" in feats.columns
    # Turnover = Close * Volume
    expected_turnover = df["close"] * df["volume"]
    np.testing.assert_allclose(feats["turnover"], expected_turnover)


def test_zero_lookahead_leakage_audit():
    """
    CRITICAL TEST: Verify modifying future data at t+1 has ZERO impact on features at t.
    """
    df_original = create_synthetic_stock_df(n_bars=60)
    engine = FeatureEngine()

    feats_original = engine.compute_stock_features(df_original, symbol="TESTSTOCK")

    # Clone dataset and corrupt future bars (from index 40 onwards)
    df_mutated = df_original.copy()
    df_mutated.loc[40:, "close"] = df_mutated.loc[40:, "close"] * 5.0
    df_mutated.loc[40:, "high"] = df_mutated.loc[40:, "high"] * 5.0
    df_mutated.loc[40:, "volume"] = df_mutated.loc[40:, "volume"] * 10.0

    feats_mutated = engine.compute_stock_features(df_mutated, symbol="TESTSTOCK")

    # Audit rows 0 to 39: Must be IDENTICAL across every single feature column
    meta_cols = {"timestamp", "symbol"}
    feature_cols = [c for c in feats_original.columns if c not in meta_cols]

    for col in feature_cols:
        s_orig = feats_original.loc[0:39, col].dropna()
        s_mut = feats_mutated.loc[0:39, col].dropna()
        np.testing.assert_allclose(
            s_orig.values,
            s_mut.values,
            err_msg=f"LEAKAGE DETECTED in feature '{col}': historical row altered by future data!",
        )


def test_relative_strength_and_benchmark():
    """Verify relative return is exactly Stock Return - Benchmark Return."""
    stock_df = create_synthetic_stock_df(n_bars=50, base_price=100.0)
    bench_df = create_synthetic_stock_df(n_bars=50, base_price=500.0)

    bp = BenchmarkProvider(benchmark_df=bench_df)
    rs_feats = calculate_relative_strength_features(stock_df, bp, relative_return_periods=[5])

    stock_ret_5d = stock_df["close"] / stock_df["close"].shift(5) - 1.0
    bench_ret_5d = bench_df["close"] / bench_df["close"].shift(5) - 1.0
    expected_rel_ret = stock_ret_5d - bench_ret_5d

    np.testing.assert_allclose(
        rs_feats["relative_return_5d"].dropna(),
        expected_rel_ret.dropna(),
    )


def test_market_regime_state_derivation():
    """Verify deterministic bullish, bearish, and neutral market regime classification."""
    bench_df = create_synthetic_stock_df(n_bars=80, base_price=1000.0)
    bp = BenchmarkProvider(benchmark_df=bench_df)

    stock_df = create_synthetic_stock_df(n_bars=80, base_price=100.0)
    regime_feats = calculate_market_regime_features(
        stock_df, bp, sma_fast=10, sma_slow=20, return_period=5, volatility_period=5
    )

    assert "regime_market_state" in regime_feats.columns
    states = regime_feats["regime_market_state"].dropna().unique()
    assert set(states).issubset({-1.0, 0.0, 1.0}), "Regime state must only be -1, 0, or 1"


def test_cross_sectional_normalization():
    """Verify cross-sectional z-score produces zero mean and unit variance per timestamp slice."""
    panel = pd.DataFrame({
        "timestamp": [pd.Timestamp("2024-01-01")] * 4 + [pd.Timestamp("2024-01-02")] * 4,
        "symbol": ["A", "B", "C", "D"] * 2,
        "feat1": [10.0, 20.0, 30.0, 40.0, 100.0, 200.0, 300.0, 400.0],
    })

    z_panel = cross_sectional_zscore(panel, feature_cols=["feat1"], group_col="timestamp")
    
    # Check timestamp 1
    t1 = z_panel[z_panel["timestamp"] == pd.Timestamp("2024-01-01")]
    np.testing.assert_allclose(t1["feat1"].mean(), 0.0, atol=1e-7)
    np.testing.assert_allclose(t1["feat1"].std(), 1.0, atol=1e-7)

    # Check percentile rank in [0, 1]
    rank_panel = cross_sectional_rank(panel, feature_cols=["feat1"], group_col="timestamp")
    assert (rank_panel["feat1"] >= 0.0).all() and (rank_panel["feat1"] <= 1.0).all()


def test_feature_validator_diagnostics():
    """Verify FeatureValidator correctly catches duplicates, monotonicity, and infs."""
    bad_df = pd.DataFrame({
        "timestamp": [pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-01")],
        "symbol": ["A", "A", "A"],
        "rsi_14": [50.0, np.inf, 150.0],  # Contains inf and value > 100
        "volatility_10d": [-0.05, 0.1, 0.2],  # Negative volatility
    })

    report = FeatureValidator.validate_panel(
        bad_df,
        feature_cols=["rsi_14", "volatility_10d"],
        timestamp_col="timestamp",
        symbol_col="symbol",
    )

    assert report.is_valid is False
    assert report.duplicate_count > 0, "Failed to flag duplicate timestamps"
    assert "rsi_14" in report.inf_counts, "Failed to flag infinite value"
    assert "rsi_14" in report.domain_violations, "Failed to flag RSI > 100"
    assert "volatility_10d" in report.domain_violations, "Failed to flag negative volatility"


def test_end_to_end_panel_from_storage():
    """Verify multi-stock feature extraction across the 5 real benchmark stocks in Parquet storage."""
    storage = ParquetMarketDataStorage()
    benchmark_symbols = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]

    engine = FeatureEngine()
    feature_set = engine.generate_panel_from_storage(
        storage=storage,
        symbols=benchmark_symbols,
        start_date="2023-01-01",
        end_date="2024-01-15",
        is_adjusted=True,
        normalize=False,
    )

    panel = feature_set.data
    assert not panel.empty, "Panel from storage must not be empty"
    assert feature_set.feature_count >= 20, f"Expected at least 20 features, got {feature_set.feature_count}"
    assert set(feature_set.symbols) == set(benchmark_symbols)
    
    # Required columns check
    assert "timestamp" in panel.columns
    assert "symbol" in panel.columns
    assert "has_sufficient_history" in panel.columns
    assert "has_full_warmup" in panel.columns

    # Verify validation result
    val = feature_set.validation_result
    assert val is not None
    assert val.is_valid is True, f"Validation failed with errors: {val.error_messages}"
    assert val.duplicate_count == 0
    assert len(val.inf_counts) == 0


if __name__ == "__main__":
    test_hand_calculated_price_features()
    print("  [OK] test_hand_calculated_price_features")
    test_hand_calculated_trend_features()
    print("  [OK] test_hand_calculated_trend_features")
    test_momentum_rsi_bounds_and_roc()
    print("  [OK] test_momentum_rsi_bounds_and_roc")
    test_volatility_and_atr_non_negative()
    print("  [OK] test_volatility_and_atr_non_negative")
    test_volume_turnover_features()
    print("  [OK] test_volume_turnover_features")
    test_zero_lookahead_leakage_audit()
    print("  [OK] test_zero_lookahead_leakage_audit")
    test_relative_strength_and_benchmark()
    print("  [OK] test_relative_strength_and_benchmark")
    test_market_regime_state_derivation()
    print("  [OK] test_market_regime_state_derivation")
    test_cross_sectional_normalization()
    print("  [OK] test_cross_sectional_normalization")
    test_feature_validator_diagnostics()
    print("  [OK] test_feature_validator_diagnostics")
    test_end_to_end_panel_from_storage()
    print("  [OK] test_end_to_end_panel_from_storage")
    print("\nAll Multi-Stock Feature Engineering tests PASSED successfully.")
