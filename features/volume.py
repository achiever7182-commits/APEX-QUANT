"""
features/volume.py — Vectorized volume and liquidity activity feature calculations.

Computes:
  - 1-day volume percentage change: volume_change_1d
  - Rolling volume moving averages: volume_sma_10, volume_sma_20
  - Volume ratio relative to rolling average: volume_to_sma_20_ratio
  - Volume momentum over 5 days: volume_momentum_5d
  - Daily turnover: Close * Volume
  - Rolling turnover moving average: turnover_sma_20d

Strict zero lookahead. Does not fabricate unavailable market fields (e.g. delivery data).
"""

from __future__ import annotations

from typing import Dict, List, Optional
import numpy as np
import pandas as pd

from features.models import FeatureCategory, FeatureMetadata


VOLUME_FEATURE_METADATA: Dict[str, FeatureMetadata] = {}


def register_volume_feature(name: str, lookback: int, desc: str, **kwargs) -> FeatureMetadata:
    meta = FeatureMetadata(
        name=name,
        category=FeatureCategory.VOLUME,
        lookback_bars=lookback,
        description=desc,
        requires_adjusted=False,  # Volume is typically raw traded shares
        **kwargs,
    )
    VOLUME_FEATURE_METADATA[name] = meta
    return meta


def calculate_volume_features(
    df: pd.DataFrame,
    volume_sma_periods: Optional[List[int]] = None,
    volume_momentum_period: int = 5,
    volume_col: str = "volume",
    close_col: str = "close",
) -> pd.DataFrame:
    """
    Compute volume and turnover metrics.

    Parameters:
        df: DataFrame containing volume and close price series sorted ascending.
        volume_sma_periods: Lookbacks for volume SMAs (default: [10, 20]).
        volume_momentum_period: Lookback for volume momentum (default: 5).
        volume_col, close_col: Column names.

    Returns:
        DataFrame containing volume features.
    """
    if volume_sma_periods is None:
        volume_sma_periods = [10, 20]

    feats = pd.DataFrame(index=df.index)
    if volume_col not in df.columns:
        return feats

    vol = df[volume_col].astype(float)
    close = df[close_col].astype(float) if close_col in df.columns else None

    # 1-day percentage volume change: V_t / V_{t-1} - 1
    feats["volume_change_1d"] = vol / (vol.shift(1) + 1e-9) - 1.0
    if "volume_change_1d" not in VOLUME_FEATURE_METADATA:
        register_volume_feature("volume_change_1d", 1, "1-day percentage change in trading volume")

    # Volume SMAs and volume ratios
    for p in volume_sma_periods:
        sma_col = f"volume_sma_{p}d"
        vol_sma = vol.rolling(window=p, min_periods=p).mean()
        feats[sma_col] = vol_sma
        if sma_col not in VOLUME_FEATURE_METADATA:
            register_volume_feature(
                sma_col,
                p,
                f"{p}-day Simple Moving Average of traded volume",
                is_bounded=True,
                lower_bound=0.0,
            )

        ratio_col = f"volume_to_sma_{p}_ratio"
        feats[ratio_col] = vol / (vol_sma + 1e-9)
        if ratio_col not in VOLUME_FEATURE_METADATA:
            register_volume_feature(
                ratio_col,
                p,
                f"Ratio of current volume to {p}-day volume SMA (V / SMA_V)",
                is_bounded=True,
                lower_bound=0.0,
            )

    # Volume momentum over k periods: V_t / V_{t-k} - 1
    col_mom = f"volume_momentum_{volume_momentum_period}d"
    feats[col_mom] = vol / (vol.shift(volume_momentum_period) + 1e-9) - 1.0
    if col_mom not in VOLUME_FEATURE_METADATA:
        register_volume_feature(
            col_mom,
            volume_momentum_period,
            f"{volume_momentum_period}-day volume momentum (V_t / V_{{t-k}} - 1)",
        )

    # Daily turnover: Close * Volume
    if close is not None:
        turnover = close * vol
        feats["turnover"] = turnover
        if "turnover" not in VOLUME_FEATURE_METADATA:
            register_volume_feature(
                "turnover",
                1,
                "Estimated daily turnover (Close * Volume)",
                is_bounded=True,
                lower_bound=0.0,
            )

        # 20-day average turnover
        feats["turnover_sma_20d"] = turnover.rolling(window=20, min_periods=20).mean()
        if "turnover_sma_20d" not in VOLUME_FEATURE_METADATA:
            register_volume_feature(
                "turnover_sma_20d",
                20,
                "20-day Simple Moving Average of daily turnover",
                is_bounded=True,
                lower_bound=0.0,
            )

    return feats
