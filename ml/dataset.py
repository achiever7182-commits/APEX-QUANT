"""
ml/dataset.py — 3-class target labeling and chronological dataset splitting.

Creates 3 target classes:
  - 2: BUY  (future_return >= buy_threshold)
  - 1: HOLD (between sell_threshold and buy_threshold)
  - 0: SELL (future_return <= sell_threshold)

Enforces strictly chronological Train / Validation / Test splits without data leakage.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence
import numpy as np
import pandas as pd

from core.strategy import MarketData
from ml.feature_engineering import extract_features_df, FEATURE_NAMES

LABEL_SELL = 0
LABEL_HOLD = 1
LABEL_BUY = 2

LABEL_MAP = {
    LABEL_SELL: "SELL",
    LABEL_HOLD: "HOLD",
    LABEL_BUY: "BUY",
}


@dataclass
class MLDataset:
    X_train: np.ndarray
    y_train: np.ndarray
    X_val: np.ndarray
    y_val: np.ndarray
    X_test: np.ndarray
    y_test: np.ndarray
    feature_names: list[str]
    train_candles: list[MarketData]
    val_candles: list[MarketData]
    test_candles: list[MarketData]
    horizon: int
    buy_threshold: float
    sell_threshold: float


def chronological_split(
    X: np.ndarray,
    y: np.ndarray,
    candles: Sequence[MarketData],
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, list[MarketData], list[MarketData], list[MarketData]]:
    """
    Split time-series data chronologically (NO random shuffling).
    Default: 70% Train, 15% Validation, 15% Test.
    """
    n = len(X)
    train_end = int(n * train_ratio)
    val_end = int(n * (train_ratio + val_ratio))

    X_train, y_train = X[:train_end], y[:train_end]
    X_val, y_val = X[train_end:val_end], y[train_end:val_end]
    X_test, y_test = X[val_end:], y[val_end:]

    c_train = list(candles[:train_end])
    c_val = list(candles[train_end:val_end])
    c_test = list(candles[val_end:])

    return X_train, y_train, X_val, y_val, X_test, y_test, c_train, c_val, c_test


def create_ml_dataset(
    candles: list[MarketData],
    horizon: int = 3,
    buy_threshold: float = 0.005,      # +0.5%
    sell_threshold: float = -0.005,    # -0.5%
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
) -> MLDataset:
    """
    Build feature matrix X and 3-class target y from a list of candles,
    then perform a chronological train/val/test split.

    CRITICAL LOOKAHEAD ENFORCEMENT:
    -------------------------------
    - At index i, features X[i] are engineered using candles[0 ... i].
    - Target label y[i] is computed strictly from future return (close[i+horizon] / close[i] - 1).
    - Future return is NEVER included in X.
    """
    if len(candles) < 100:
        raise ValueError(f"Insufficient candles: {len(candles)}. Need at least 100.")

    # Convert to DataFrame for vectorized indicator calculations
    records = [
        {
            "timestamp": c.timestamp,
            "open": float(c.open),
            "high": float(c.high),
            "low": float(c.low),
            "close": float(c.close),
            "volume": float(c.volume),
        }
        for c in candles
    ]
    df = pd.DataFrame(records)
    df_feat, feature_names = extract_features_df(df)

    # Calculate future return label (for training labels only)
    future_close = df_feat["close"].shift(-horizon)
    current_close = df_feat["close"]
    future_return = (future_close - current_close) / current_close

    # 3-Class Target Labeling
    conditions = [
        future_return >= buy_threshold,
        future_return <= sell_threshold,
    ]
    choices = [LABEL_BUY, LABEL_SELL]
    # Default is HOLD (LABEL_HOLD = 1)
    target = np.select(conditions, choices, default=LABEL_HOLD)
    df_feat["target"] = target

    # Drop rows where future_return is NaN (last H rows) and warmup rows where features are NaN
    valid_mask = ~df_feat["return_20" if "return_20" in df_feat.columns else "return_10"].isna() & ~future_return.isna()
    df_valid = df_feat[valid_mask].reset_index(drop=True)

    # Valid matching candles
    valid_indices = df_valid["timestamp"].to_dict()
    timestamp_to_candle = {c.timestamp: c for c in candles}
    valid_candles = [timestamp_to_candle[ts] for ts in df_valid["timestamp"] if ts in timestamp_to_candle]

    X = df_valid[feature_names].values.astype(np.float32)
    y = df_valid["target"].values.astype(np.int64)

    # Chronological Split
    X_tr, y_tr, X_v, y_v, X_te, y_te, c_tr, c_v, c_te = chronological_split(
        X, y, valid_candles, train_ratio=train_ratio, val_ratio=val_ratio
    )

    return MLDataset(
        X_train=X_tr,
        y_train=y_tr,
        X_val=X_v,
        y_val=y_v,
        X_test=X_te,
        y_test=y_te,
        feature_names=feature_names,
        train_candles=c_tr,
        val_candles=c_v,
        test_candles=c_te,
        horizon=horizon,
        buy_threshold=buy_threshold,
        sell_threshold=sell_threshold,
    )
