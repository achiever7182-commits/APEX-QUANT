"""
features/volatility.py — Vectorized volatility and risk feature calculations.

Computes:
  - Rolling standard deviation of daily returns: 10, 20, 60 days
  - Average True Range (ATR 14) using Wilder's smoothing
  - ATR percentage of close price: atr_pct_14
  - Normalized daily High-Low range: (High - Low) / Close
  - Downside volatility (semi-deviation of negative returns over 20 days)

Zero lookahead: Only past and current observations are incorporated.
"""

from __future__ import annotations

from typing import Dict, List, Optional
import numpy as np
import pandas as pd

from features.models import FeatureCategory, FeatureMetadata


VOLATILITY_FEATURE_METADATA: Dict[str, FeatureMetadata] = {}


def register_volatility_feature(name: str, lookback: int, desc: str, **kwargs) -> FeatureMetadata:
    meta = FeatureMetadata(
        name=name,
        category=FeatureCategory.VOLATILITY,
        lookback_bars=lookback,
        description=desc,
        requires_adjusted=True,
        **kwargs,
    )
    VOLATILITY_FEATURE_METADATA[name] = meta
    return meta


def calculate_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> pd.Series:
    """
    Calculate Average True Range using Wilder's smoothing.
    
    True Range = max(H - L, |H - C_{t-1}|, |L - C_{t-1}|)
    """
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = tr.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    return atr


def calculate_volatility_features(
    df: pd.DataFrame,
    volatility_periods: Optional[List[int]] = None,
    atr_period: int = 14,
    downside_vol_period: int = 20,
    close_col: str = "close",
    high_col: str = "high",
    low_col: str = "low",
) -> pd.DataFrame:
    """
    Compute volatility and risk metrics.

    Parameters:
        df: DataFrame containing price series sorted ascending.
        volatility_periods: Lookback windows for rolling return std (default: [10, 20, 60]).
        atr_period: Period for ATR calculation (default: 14).
        downside_vol_period: Lookback window for semi-deviation (default: 20).
        close_col, high_col, low_col: Column names.

    Returns:
        DataFrame containing volatility features.
    """
    if volatility_periods is None:
        volatility_periods = [10, 20, 60]

    feats = pd.DataFrame(index=df.index)
    close = df[close_col].astype(float)
    high = df[high_col].astype(float) if high_col in df.columns else close
    low = df[low_col].astype(float) if low_col in df.columns else close

    # 1-day percentage return for volatility calculations
    ret_1d = close.pct_change(1)

    # Rolling standard deviation of daily returns
    for p in volatility_periods:
        col_name = f"volatility_{p}d"
        feats[col_name] = ret_1d.rolling(window=p, min_periods=p).std()
        if col_name not in VOLATILITY_FEATURE_METADATA:
            register_volatility_feature(
                col_name,
                p,
                f"{p}-day rolling standard deviation of daily returns",
                is_bounded=True,
                lower_bound=0.0,
            )

    # Average True Range
    atr_series = calculate_atr(high, low, close, period=atr_period)
    col_atr = f"atr_{atr_period}"
    feats[col_atr] = atr_series
    if col_atr not in VOLATILITY_FEATURE_METADATA:
        register_volatility_feature(
            col_atr,
            atr_period,
            f"{atr_period}-day Average True Range (Wilder)",
            is_bounded=True,
            lower_bound=0.0,
        )

    # ATR as percentage of close price
    col_atr_pct = f"atr_pct_{atr_period}"
    feats[col_atr_pct] = (atr_series / (close + 1e-9)) * 100.0
    if col_atr_pct not in VOLATILITY_FEATURE_METADATA:
        register_volatility_feature(
            col_atr_pct,
            atr_period,
            f"{atr_period}-day ATR expressed as percentage of close price",
            is_bounded=True,
            lower_bound=0.0,
        )

    # Daily high-low range normalized by close: (High - Low) / Close
    feats["candle_range_pct"] = ((high - low) / (close + 1e-9)) * 100.0
    if "candle_range_pct" not in VOLATILITY_FEATURE_METADATA:
        register_volatility_feature(
            "candle_range_pct",
            1,
            "Daily candle high-to-low range normalized as % of close",
            is_bounded=True,
            lower_bound=0.0,
        )

    # Downside volatility: standard deviation of negative returns over lookback
    neg_ret = ret_1d.clip(upper=0.0)
    feats[f"downside_volatility_{downside_vol_period}d"] = neg_ret.rolling(
        window=downside_vol_period, min_periods=downside_vol_period
    ).std()
    col_downside = f"downside_volatility_{downside_vol_period}d"
    if col_downside not in VOLATILITY_FEATURE_METADATA:
        register_volatility_feature(
            col_downside,
            downside_vol_period,
            f"{downside_vol_period}-day downside semi-deviation of negative returns",
            is_bounded=True,
            lower_bound=0.0,
        )

    return feats
