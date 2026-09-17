"""
features/momentum.py — Vectorized momentum and oscillator feature calculations.

Computes:
  - Relative Strength Index (RSI 14) using Wilder's exponential smoothing
  - Rate of Change (ROC): 5, 10, 20, 60
  - Absolute price momentum: 5, 10, 20, 60
  - Normalized momentum: (Close_t - Close_{t-k}) / Close_t
  - RSI Momentum: RSI_t - RSI_{t-5}

Zero lookahead: All calculations at candle t use strictly data <= t.
Missing early data remains NaN and is never backfilled from future periods.
"""

from __future__ import annotations

from typing import Dict, List, Optional
import numpy as np
import pandas as pd

from features.models import FeatureCategory, FeatureMetadata


MOMENTUM_FEATURE_METADATA: Dict[str, FeatureMetadata] = {}


def register_momentum_feature(name: str, lookback: int, desc: str, **kwargs) -> FeatureMetadata:
    meta = FeatureMetadata(
        name=name,
        category=FeatureCategory.MOMENTUM,
        lookback_bars=lookback,
        description=desc,
        requires_adjusted=True,
        **kwargs,
    )
    MOMENTUM_FEATURE_METADATA[name] = meta
    return meta


def calculate_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """
    Calculate Wilder's Relative Strength Index (RSI).
    
    Uses alpha = 1 / period exponential moving average on positive and negative changes.
    Output is strictly bounded between [0.0, 100.0].
    """
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    # Wilder's smoothing: alpha = 1/period, adjust=False
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / (avg_loss + 1e-12)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi


def calculate_momentum_features(
    df: pd.DataFrame,
    rsi_period: int = 14,
    roc_periods: Optional[List[int]] = None,
    mom_periods: Optional[List[int]] = None,
    close_col: str = "close",
) -> pd.DataFrame:
    """
    Calculate momentum indicators.

    Parameters:
        df: DataFrame containing price series sorted ascending.
        rsi_period: Lookback for RSI (default: 14).
        roc_periods: Lookback windows for Rate of Change (default: [5, 10, 20, 60]).
        mom_periods: Lookback windows for price momentum (default: [5, 10, 20, 60]).
        close_col: Name of close price column.

    Returns:
        DataFrame containing momentum features.
    """
    if roc_periods is None:
        roc_periods = [5, 10, 20, 60]
    if mom_periods is None:
        mom_periods = [5, 10, 20, 60]

    feats = pd.DataFrame(index=df.index)
    close = df[close_col].astype(float)

    # RSI
    rsi_col = f"rsi_{rsi_period}"
    rsi_series = calculate_rsi(close, period=rsi_period)
    feats[rsi_col] = rsi_series
    if rsi_col not in MOMENTUM_FEATURE_METADATA:
        register_momentum_feature(
            rsi_col,
            rsi_period,
            f"Relative Strength Index ({rsi_period}-period Wilder)",
            is_bounded=True,
            lower_bound=0.0,
            upper_bound=100.0,
        )

    # RSI Momentum: change in RSI over 5 bars
    feats["rsi_momentum_5d"] = rsi_series - rsi_series.shift(5)
    if "rsi_momentum_5d" not in MOMENTUM_FEATURE_METADATA:
        register_momentum_feature("rsi_momentum_5d", rsi_period + 5, "5-day change in RSI (RSI_t - RSI_{t-5})")

    # Rate of Change (ROC in %): (Close_t - Close_{t-k}) / Close_{t-k} * 100
    for k in roc_periods:
        col_name = f"roc_{k}d"
        feats[col_name] = ((close - close.shift(k)) / (close.shift(k) + 1e-9)) * 100.0
        if col_name not in MOMENTUM_FEATURE_METADATA:
            register_momentum_feature(col_name, k, f"{k}-day Rate of Change percentage")

    # Normalized Momentum: (Close_t - Close_{t-k}) / Close_t
    for k in mom_periods:
        col_name = f"momentum_norm_{k}d"
        feats[col_name] = (close - close.shift(k)) / (close + 1e-9)
        if col_name not in MOMENTUM_FEATURE_METADATA:
            register_momentum_feature(col_name, k, f"{k}-day Normalized price momentum (P_t - P_{{t-k}}) / P_t")

    # Rolling return momentum (acceleration): return_5d - return_5d shifted by 5d
    ret_5d = close / close.shift(5) - 1.0
    feats["return_acceleration_5d"] = ret_5d - ret_5d.shift(5)
    if "return_acceleration_5d" not in MOMENTUM_FEATURE_METADATA:
        register_momentum_feature("return_acceleration_5d", 10, "5-day return acceleration (Ret5_t - Ret5_{t-5})")

    return feats
