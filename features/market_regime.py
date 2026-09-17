"""
features/market_regime.py — Vectorized macro/market regime features derived from benchmark.

Computes:
  - regime_bench_above_sma50: 1 if benchmark Close > SMA50 else 0
  - regime_bench_above_sma200: 1 if benchmark Close > SMA200 else 0
  - regime_bench_return_20d: 20-day benchmark percentage return
  - regime_bench_volatility_20d: 20-day rolling standard deviation of daily benchmark returns
  - regime_market_state:
      +1 (Bullish): Close > SMA50 and 20-day return > 0
      -1 (Bearish): Close < SMA50 and 20-day return < 0
       0 (Neutral): Otherwise

Strict zero lookahead. Computed deterministically from historical benchmark data up to t.
"""

from __future__ import annotations

from typing import Dict, Optional
import numpy as np
import pandas as pd

from features.models import FeatureCategory, FeatureMetadata
from features.relative_strength import BenchmarkProvider


REGIME_FEATURE_METADATA: Dict[str, FeatureMetadata] = {}


def register_regime_feature(name: str, lookback: int, desc: str, **kwargs) -> FeatureMetadata:
    meta = FeatureMetadata(
        name=name,
        category=FeatureCategory.MARKET_REGIME,
        lookback_bars=lookback,
        description=desc,
        requires_adjusted=True,
        **kwargs,
    )
    REGIME_FEATURE_METADATA[name] = meta
    return meta


def calculate_market_regime_features(
    stock_df: pd.DataFrame,
    benchmark_provider: BenchmarkProvider,
    sma_fast: int = 50,
    sma_slow: int = 200,
    return_period: int = 20,
    volatility_period: int = 20,
    timestamp_col: str = "timestamp",
) -> pd.DataFrame:
    """
    Calculate market regime features aligned with stock timestamps.

    Parameters:
        stock_df: Stock DataFrame sorted ascending.
        benchmark_provider: Configured BenchmarkProvider instance.
        sma_fast, sma_slow: Benchmark SMA periods (default 50, 200).
        return_period: Lookback for benchmark return (default 20).
        volatility_period: Lookback for benchmark return std (default 20).
        timestamp_col: Column name of timestamp.

    Returns:
        DataFrame containing market regime features aligned with stock_df.
    """
    feats = pd.DataFrame(index=stock_df.index)
    bench_df = benchmark_provider.get_benchmark_series().copy()

    bench_close = bench_df["close"].astype(float)
    bench_ret_1d = bench_close.pct_change(1)

    # 1. Benchmark SMAs
    bench_sma_fast = bench_close.rolling(window=sma_fast, min_periods=sma_fast).mean()
    bench_sma_slow = bench_close.rolling(window=sma_slow, min_periods=sma_slow).mean()

    above_fast = (bench_close > bench_sma_fast).astype(float)
    above_slow = (bench_close > bench_sma_slow).astype(float)

    # 2. Benchmark return & volatility
    bench_ret_k = bench_close / bench_close.shift(return_period) - 1.0
    bench_vol_k = bench_ret_1d.rolling(window=volatility_period, min_periods=volatility_period).std()

    # 3. Market state: +1 (bullish), -1 (bearish), 0 (neutral)
    is_bull = (bench_close > bench_sma_fast) & (bench_ret_k > 0.0)
    is_bear = (bench_close < bench_sma_fast) & (bench_ret_k < 0.0)
    market_state = np.where(is_bull, 1.0, np.where(is_bear, -1.0, 0.0))

    # Align to stock dates
    bench_dates = pd.to_datetime(bench_df["timestamp"]).dt.date
    stock_dates = pd.to_datetime(stock_df[timestamp_col]).dt.date

    feats[f"regime_bench_above_sma{sma_fast}"] = stock_dates.map(
        pd.Series(above_fast.values, index=bench_dates)
    ).astype(float)
    register_regime_feature(
        f"regime_bench_above_sma{sma_fast}",
        sma_fast,
        f"Binary indicator: Benchmark Close > {sma_fast}-day SMA",
        is_bounded=True,
        lower_bound=0.0,
        upper_bound=1.0,
    )

    feats[f"regime_bench_above_sma{sma_slow}"] = stock_dates.map(
        pd.Series(above_slow.values, index=bench_dates)
    ).astype(float)
    register_regime_feature(
        f"regime_bench_above_sma{sma_slow}",
        sma_slow,
        f"Binary indicator: Benchmark Close > {sma_slow}-day SMA",
        is_bounded=True,
        lower_bound=0.0,
        upper_bound=1.0,
    )

    feats[f"regime_bench_return_{return_period}d"] = stock_dates.map(
        pd.Series(bench_ret_k.values, index=bench_dates)
    ).astype(float)
    register_regime_feature(
        f"regime_bench_return_{return_period}d",
        return_period,
        f"{return_period}-day percentage return of benchmark index",
    )

    feats[f"regime_bench_volatility_{volatility_period}d"] = stock_dates.map(
        pd.Series(bench_vol_k.values, index=bench_dates)
    ).astype(float)
    register_regime_feature(
        f"regime_bench_volatility_{volatility_period}d",
        volatility_period,
        f"{volatility_period}-day rolling volatility of benchmark index",
        is_bounded=True,
        lower_bound=0.0,
    )

    feats["regime_market_state"] = stock_dates.map(
        pd.Series(market_state, index=bench_dates)
    ).astype(float)
    register_regime_feature(
        "regime_market_state",
        max(sma_fast, return_period),
        "Market regime classification: +1 Bullish, 0 Neutral, -1 Bearish",
        is_bounded=True,
        lower_bound=-1.0,
        upper_bound=1.0,
    )

    return feats
