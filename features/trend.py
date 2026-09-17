"""
features/trend.py — Vectorized trend and moving average feature calculations.

Computes:
  - Simple Moving Averages (SMA): 5, 10, 20, 50, 100, 200
  - Exponential Moving Averages (EMA): 9, 21, 50
  - Price-to-SMA ratios (e.g. Close / SMA20 - 1)
  - Moving average spreads and crossovers (e.g. EMA9 / EMA21 - 1)

Zero lookahead: All rolling and ewm operations are right-aligned (only past data).
"""

from __future__ import annotations

from typing import Dict, List, Optional
import numpy as np
import pandas as pd

from features.models import FeatureCategory, FeatureMetadata


TREND_FEATURE_METADATA: Dict[str, FeatureMetadata] = {}


def register_trend_feature(name: str, lookback: int, desc: str, **kwargs) -> FeatureMetadata:
    meta = FeatureMetadata(
        name=name,
        category=FeatureCategory.TREND,
        lookback_bars=lookback,
        description=desc,
        requires_adjusted=True,
        **kwargs,
    )
    TREND_FEATURE_METADATA[name] = meta
    return meta


def calculate_trend_features(
    df: pd.DataFrame,
    sma_periods: Optional[List[int]] = None,
    ema_periods: Optional[List[int]] = None,
    close_col: str = "close",
) -> pd.DataFrame:
    """
    Compute trend features including SMAs, EMAs, price-to-MA ratios, and MA spreads.

    Parameters:
        df: DataFrame containing price series sorted ascending.
        sma_periods: Periods for SMA calculation (default: [5, 10, 20, 50, 100, 200]).
        ema_periods: Periods for EMA calculation (default: [9, 21, 50]).
        close_col: Name of close price column.

    Returns:
        DataFrame containing trend features.
    """
    if sma_periods is None:
        sma_periods = [5, 10, 20, 50, 100, 200]
    if ema_periods is None:
        ema_periods = [9, 21, 50]

    feats = pd.DataFrame(index=df.index)
    close = df[close_col].astype(float)

    # Compute SMAs and price-to-SMA ratios
    sma_series: Dict[int, pd.Series] = {}
    for p in sma_periods:
        sma = close.rolling(window=p, min_periods=p).mean()
        sma_series[p] = sma
        col_name = f"sma_{p}"
        feats[col_name] = sma
        if col_name not in TREND_FEATURE_METADATA:
            register_trend_feature(col_name, p, f"{p}-day Simple Moving Average")

        # Price-to-SMA ratio (percentage difference from MA)
        ratio_col = f"price_to_sma_{p}_ratio"
        feats[ratio_col] = close / (sma + 1e-9) - 1.0
        if ratio_col not in TREND_FEATURE_METADATA:
            register_trend_feature(ratio_col, p, f"Close price relative to {p}-day SMA (Close/SMA - 1)")

    # Compute EMAs
    ema_series: Dict[int, pd.Series] = {}
    for p in ema_periods:
        # ewm with span=p, min_periods=p, adjust=False (standard technical analysis recurrence)
        ema = close.ewm(span=p, min_periods=p, adjust=False).mean()
        ema_series[p] = ema
        col_name = f"ema_{p}"
        feats[col_name] = ema
        if col_name not in TREND_FEATURE_METADATA:
            register_trend_feature(col_name, p, f"{p}-day Exponential Moving Average")

        ratio_col = f"price_to_ema_{p}_ratio"
        feats[ratio_col] = close / (ema + 1e-9) - 1.0
        if ratio_col not in TREND_FEATURE_METADATA:
            register_trend_feature(ratio_col, p, f"Close price relative to {p}-day EMA (Close/EMA - 1)")

    # Moving average spreads
    if 9 in ema_series and 21 in ema_series:
        feats["ema_9_to_21_spread"] = ema_series[9] / (ema_series[21] + 1e-9) - 1.0
        if "ema_9_to_21_spread" not in TREND_FEATURE_METADATA:
            register_trend_feature("ema_9_to_21_spread", 21, "Spread between EMA 9 and EMA 21 (EMA9/EMA21 - 1)")

    if 20 in sma_series and 50 in sma_series:
        feats["sma_20_to_50_spread"] = sma_series[20] / (sma_series[50] + 1e-9) - 1.0
        if "sma_20_to_50_spread" not in TREND_FEATURE_METADATA:
            register_trend_feature("sma_20_to_50_spread", 50, "Spread between SMA 20 and SMA 50 (SMA20/SMA50 - 1)")

    if 50 in sma_series and 200 in sma_series:
        feats["sma_50_to_200_spread"] = sma_series[50] / (sma_series[200] + 1e-9) - 1.0
        if "sma_50_to_200_spread" not in TREND_FEATURE_METADATA:
            register_trend_feature("sma_50_to_200_spread", 200, "Golden/Death cross spread: SMA 50 vs SMA 200 (SMA50/SMA200 - 1)")

    return feats
