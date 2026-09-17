"""
features/normalization.py — Optional cross-sectional feature transformations.

Provides:
  - Cross-sectional z-score: (x - mean_t) / std_t per timestamp
  - Cross-sectional percentile rank: rank_t / count_t in [0.0, 1.0] per timestamp
  - Cross-sectional winsorization: clipping tails at quantiles per timestamp

STRICT POINT-IN-TIME GUARANTEE:
  Transformations are evaluated INDEPENDENTLY within each timestamp group.
  Stocks at date T are normalized using ONLY the cross-section of stocks present at date T.
  Future or past observations NEVER enter the normalization parameters for date T.
"""

from __future__ import annotations

from typing import List, Sequence, Tuple
import numpy as np
import pandas as pd


def cross_sectional_zscore(
    df: pd.DataFrame,
    feature_cols: Sequence[str],
    group_col: str = "timestamp",
    eps: float = 1e-8,
) -> pd.DataFrame:
    """
    Standardize features across instruments separately for each timestamp.
    
    Resulting features have zero mean and unit variance across stocks on date t.
    """
    out = df.copy()
    for col in feature_cols:
        if col not in out.columns:
            continue
        
        # Group by timestamp and compute cross-sectional mean and std
        means = out.groupby(group_col)[col].transform("mean")
        stds = out.groupby(group_col)[col].transform("std")
        
        # Where std is 0 or NaN (e.g. single stock in slice), fill with 0.0
        z = (out[col] - means) / (stds + eps)
        out[col] = z.fillna(0.0)
    return out


def cross_sectional_rank(
    df: pd.DataFrame,
    feature_cols: Sequence[str],
    group_col: str = "timestamp",
) -> pd.DataFrame:
    """
    Compute cross-sectional percentile rank [0.0, 1.0] separately for each timestamp.
    """
    out = df.copy()
    for col in feature_cols:
        if col not in out.columns:
            continue
        out[col] = out.groupby(group_col)[col].rank(pct=True, method="average")
    return out


def cross_sectional_winsorize(
    df: pd.DataFrame,
    feature_cols: Sequence[str],
    limits: Tuple[float, float] = (0.01, 0.01),
    group_col: str = "timestamp",
) -> pd.DataFrame:
    """
    Winsorize features by clipping extreme tails per timestamp.
    
    Parameters:
        df: Input panel DataFrame.
        feature_cols: Columns to winsorize.
        limits: (lower_percentile, upper_percentile), e.g. (0.01, 0.01) for 1st and 99th.
        group_col: Timestamp column name.
    """
    out = df.copy()
    lower_p, upper_p = limits

    def _winsorize_group(series: pd.Series) -> pd.Series:
        if series.dropna().empty:
            return series
        q_low = series.quantile(lower_p)
        q_high = series.quantile(1.0 - upper_p)
        return series.clip(lower=q_low, upper=q_high)

    for col in feature_cols:
        if col not in out.columns:
            continue
        out[col] = out.groupby(group_col, group_keys=False)[col].apply(_winsorize_group)
    return out
