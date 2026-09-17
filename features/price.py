"""
features/price.py — Vectorized price-based feature calculations.

All calculations at index t use ONLY data available up to t (zero lookahead).
Requires adjusted close/open prices where corporate actions (splits/dividends)
occur, to avoid artificial price discontinuities.
"""

from __future__ import annotations

from typing import Dict, List, Optional
import numpy as np
import pandas as pd

from features.models import FeatureCategory, FeatureMetadata


PRICE_FEATURE_METADATA: Dict[str, FeatureMetadata] = {}


def register_price_feature(name: str, lookback: int, desc: str, **kwargs) -> FeatureMetadata:
    meta = FeatureMetadata(
        name=name,
        category=FeatureCategory.PRICE,
        lookback_bars=lookback,
        description=desc,
        requires_adjusted=True,
        **kwargs,
    )
    PRICE_FEATURE_METADATA[name] = meta
    return meta


def calculate_price_features(
    df: pd.DataFrame,
    return_periods: Optional[List[int]] = None,
    close_col: str = "close",
    open_col: str = "open",
    high_col: str = "high",
    low_col: str = "low",
) -> pd.DataFrame:
    """
    Compute price returns, log returns, gap returns, and rolling price statistics.

    Parameters:
        df: DataFrame containing OHLCV series sorted ascending by timestamp.
        return_periods: List of lookback periods for simple returns (e.g. [1, 3, 5, 10, 20, 60]).
        close_col, open_col, high_col, low_col: Column names for prices.

    Returns:
        DataFrame containing only the generated price features aligned with df index.
    """
    if return_periods is None:
        return_periods = [1, 3, 5, 10, 20, 60]

    feats = pd.DataFrame(index=df.index)
    close = df[close_col].astype(float)
    open_p = df[open_col].astype(float) if open_col in df.columns else None
    high = df[high_col].astype(float) if high_col in df.columns else None
    low = df[low_col].astype(float) if low_col in df.columns else None

    # Multi-period simple returns: P_t / P_{t-k} - 1
    for k in return_periods:
        col_name = f"return_{k}d"
        feats[col_name] = close / close.shift(k) - 1.0
        if col_name not in PRICE_FEATURE_METADATA:
            register_price_feature(col_name, k, f"{k}-day percentage return")

    # 1-day log return: ln(P_t / P_{t-1})
    log_return_1d = np.log(close / close.shift(1))
    feats["log_return_1d"] = log_return_1d
    if "log_return_1d" not in PRICE_FEATURE_METADATA:
        register_price_feature("log_return_1d", 1, "1-day logarithmic return")

    # Overnight gap return: (Open_t - Close_{t-1}) / Close_{t-1}
    if open_p is not None:
        prev_close = close.shift(1)
        feats["gap_return"] = (open_p - prev_close) / prev_close
        if "gap_return" not in PRICE_FEATURE_METADATA:
            register_price_feature("gap_return", 1, "Overnight gap return (Open_t vs Close_{t-1})")

    # Rolling price statistics over 20 days
    if high is not None and low is not None:
        rolling_high_20 = high.rolling(window=20, min_periods=20).max()
        rolling_low_20 = low.rolling(window=20, min_periods=20).min()
        denom = rolling_high_20 - rolling_low_20
        # Position in 20-day high-low channel: (Close - Low20) / (High20 - Low20)
        feats["price_location_20d"] = np.where(denom > 1e-8, (close - rolling_low_20) / denom, 0.5)
        if "price_location_20d" not in PRICE_FEATURE_METADATA:
            register_price_feature(
                "price_location_20d",
                20,
                "Relative position of close within 20-day High-Low range [0, 1]",
                is_bounded=True,
                lower_bound=0.0,
                upper_bound=1.0,
            )

    return feats
