"""
features/relative_strength.py — Relative strength and benchmark performance features.

Computes:
  - Relative Return vs Benchmark:
      relative_return_5d  = Return_stock_5d  - Return_bench_5d
      relative_return_20d = Return_stock_20d - Return_bench_20d
      relative_return_60d = Return_stock_60d - Return_bench_60d
  - Benchmark Ratio: Close_stock / Close_bench
  - Relative Momentum: 20-day ROC of the (Close_stock / Close_bench) ratio

Benchmark Abstraction:
  Supports:
    1. Direct benchmark DataFrame with ['timestamp', 'close']
    2. Explicit benchmark symbol (e.g. '^NSEI', 'NIFTY50') from Parquet storage
    3. Synthetic Equal-Weighted Benchmark constructed from an available stock basket
       (e.g. the 5 benchmark stocks: RELIANCE, TCS, INFY, HDFCBANK, ICICIBANK).

Zero lookahead: All benchmark return alignments strictly match on timestamp <= t.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Union
import numpy as np
import pandas as pd

from features.models import FeatureCategory, FeatureMetadata


RELATIVE_STRENGTH_FEATURE_METADATA: Dict[str, FeatureMetadata] = {}


def register_rs_feature(name: str, lookback: int, desc: str, **kwargs) -> FeatureMetadata:
    meta = FeatureMetadata(
        name=name,
        category=FeatureCategory.RELATIVE_STRENGTH,
        lookback_bars=lookback,
        description=desc,
        requires_adjusted=True,
        **kwargs,
    )
    RELATIVE_STRENGTH_FEATURE_METADATA[name] = meta
    return meta


class BenchmarkProvider:
    """
    Manages benchmark price and return time series with zero lookahead.
    
    Can construct an equal-weighted composite if no external index symbol is provided.
    """

    def __init__(self, benchmark_df: Optional[pd.DataFrame] = None):
        """
        Parameters:
            benchmark_df: Optional DataFrame with 'timestamp' and 'close'.
        """
        self._benchmark_df: Optional[pd.DataFrame] = None
        if benchmark_df is not None:
            self.set_benchmark_data(benchmark_df)

    def set_benchmark_data(self, df: pd.DataFrame) -> None:
        """Store and prepare benchmark series indexed by normalized date/timestamp."""
        clean = df.copy()
        if "timestamp" not in clean.columns or "close" not in clean.columns:
            raise ValueError("Benchmark DataFrame must contain 'timestamp' and 'close' columns.")
        clean["timestamp"] = pd.to_datetime(clean["timestamp"])
        clean = clean.sort_values("timestamp").reset_index(drop=True)
        # Store with date as index for clean day-level matching
        clean["date"] = clean["timestamp"].dt.date
        clean = clean.drop_duplicates(subset=["date"], keep="last")
        self._benchmark_df = clean

    @classmethod
    def build_synthetic_equal_weighted_benchmark(
        cls,
        stock_dfs: Dict[str, pd.DataFrame],
        date_col: str = "timestamp",
        close_col: str = "close",
    ) -> BenchmarkProvider:
        """
        Construct a synthetic equal-weighted benchmark from a collection of stocks.

        Daily benchmark return is the arithmetic mean of available stock returns on that date.
        """
        all_dates = set()
        returns_by_symbol = {}

        for sym, df in stock_dfs.items():
            if df.empty:
                continue
            df_c = df.copy()
            df_c["dt"] = pd.to_datetime(df_c[date_col]).dt.date
            df_c = df_c.sort_values("dt").drop_duplicates(subset=["dt"], keep="last")
            df_c["ret"] = df_c[close_col].astype(float).pct_change(1)
            returns_by_symbol[sym] = df_c.set_index("dt")["ret"]

        if not returns_by_symbol:
            raise ValueError("Cannot build synthetic benchmark: no stock data provided.")

        ret_df = pd.DataFrame(returns_by_symbol)
        # Arithmetic mean return across active symbols on each date
        bench_ret = ret_df.mean(axis=1).fillna(0.0)
        
        # Cumulative index level starting at 1000.0
        bench_close = (1.0 + bench_ret).cumprod() * 1000.0
        
        bench_df = pd.DataFrame({
            "timestamp": pd.to_datetime(list(bench_close.index)),
            "close": bench_close.values,
            "return_1d": bench_ret.values,
        })
        return cls(benchmark_df=bench_df)

    def get_benchmark_series(self) -> pd.DataFrame:
        if self._benchmark_df is None:
            raise RuntimeError("Benchmark data has not been configured.")
        return self._benchmark_df


def calculate_relative_strength_features(
    stock_df: pd.DataFrame,
    benchmark_provider: BenchmarkProvider,
    relative_return_periods: Optional[List[int]] = None,
    stock_close_col: str = "close",
    timestamp_col: str = "timestamp",
) -> pd.DataFrame:
    """
    Calculate relative strength metrics against benchmark.

    Parameters:
        stock_df: Stock OHLCV DataFrame sorted ascending.
        benchmark_provider: Configured BenchmarkProvider instance.
        relative_return_periods: Periods for relative return (default: [5, 20, 60]).
        stock_close_col: Column name of stock close price.
        timestamp_col: Column name of timestamp.

    Returns:
        DataFrame aligned with stock_df containing relative strength features.
    """
    if relative_return_periods is None:
        relative_return_periods = [5, 20, 60]

    feats = pd.DataFrame(index=stock_df.index)
    bench_df = benchmark_provider.get_benchmark_series()

    stock_dates = pd.to_datetime(stock_df[timestamp_col]).dt.date
    bench_dates = pd.to_datetime(bench_df["timestamp"]).dt.date

    # Build date-aligned benchmark close series
    bench_map = pd.Series(bench_df["close"].astype(float).values, index=bench_dates)
    aligned_bench_close = stock_dates.map(bench_map).astype(float)

    stock_close = stock_df[stock_close_col].astype(float)

    # Relative returns over multiple horizons
    for k in relative_return_periods:
        stock_ret_k = stock_close / stock_close.shift(k) - 1.0
        bench_ret_k = aligned_bench_close / aligned_bench_close.shift(k) - 1.0
        
        col_rel = f"relative_return_{k}d"
        feats[col_rel] = stock_ret_k - bench_ret_k
        if col_rel not in RELATIVE_STRENGTH_FEATURE_METADATA:
            register_rs_feature(
                col_rel,
                k,
                f"{k}-day excess return over benchmark (StockRet_{k}d - BenchRet_{k}d)",
            )

    # Ratio of stock price to benchmark price
    ratio_series = stock_close / (aligned_bench_close + 1e-9)
    feats["benchmark_ratio"] = ratio_series
    if "benchmark_ratio" not in RELATIVE_STRENGTH_FEATURE_METADATA:
        register_rs_feature("benchmark_ratio", 1, "Ratio of stock close price to benchmark close (P_stock / P_bench)")

    # 20-day rate of change of the benchmark ratio
    feats["relative_ratio_roc_20d"] = (ratio_series / ratio_series.shift(20) - 1.0) * 100.0
    if "relative_ratio_roc_20d" not in RELATIVE_STRENGTH_FEATURE_METADATA:
        register_rs_feature(
            "relative_ratio_roc_20d",
            20,
            "20-day rate of change of (Stock / Benchmark) price ratio",
        )

    return feats
