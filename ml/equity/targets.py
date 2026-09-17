"""
ml/equity/targets.py — Target Generation for APEX QUANT Cross-Sectional ML.

Computes forward-looking return targets:
  - Regression: future_return_kd = Close_{t+k} / Close_t - 1.0
  - Classification (optional): binary thresholding of forward returns

CRITICAL ARCHITECTURAL DISTINCTION:
  - X (Features): Information strictly available at or before timestamp t.
  - Y (Target): Realized outcome occurring strictly AFTER timestamp t (over [t, t+k]).
  - The target is allowed to reference future prices because it is the label being predicted.
  - Features MUST NEVER use future prices or future targets.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Union
import numpy as np
import pandas as pd


class TargetGenerator:
    """
    Computes forward-looking returns and binary classification labels across instruments.
    """

    @staticmethod
    def add_forward_returns(
        df: pd.DataFrame,
        horizons: Sequence[int] = (1, 5, 10, 20),
        close_col: str = "close",
        symbol_col: str = "symbol",
        timestamp_col: str = "timestamp",
    ) -> pd.DataFrame:
        """
        Compute forward returns for each stock over configurable horizons.

        Parameters:
            df: DataFrame containing at least timestamp, symbol, and close prices.
            horizons: List of forward horizons in trading days (e.g. [1, 5, 10, 20]).
            close_col: Column name for close price.
            symbol_col: Column name for symbol.
            timestamp_col: Column name for timestamp.

        Returns:
            DataFrame with added target columns: 'target_return_{k}d'.
            The last k rows of each symbol group will have NaN for target_return_{k}d,
            reflecting that the future outcome has not yet occurred.
        """
        orig_index = df.index
        out = df.copy()
        out[timestamp_col] = pd.to_datetime(out[timestamp_col])
        out["_orig_idx"] = np.arange(len(df))
        out = out.sort_values(by=[symbol_col, timestamp_col])

        for k in horizons:
            col_name = f"target_return_{k}d"
            # Shift backwards by -k within each symbol group: row t gets close at t+k
            future_close = out.groupby(symbol_col)[close_col].shift(-k)
            out[col_name] = (future_close / out[close_col]) - 1.0

        out = out.sort_values(by="_orig_idx").drop(columns=["_orig_idx"])
        out.index = orig_index
        return out

    @staticmethod
    def add_binary_classification_target(
        df: pd.DataFrame,
        horizon: int = 5,
        threshold: float = 0.0,
        target_return_col: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Convert continuous forward return into a binary classification label.
        
        1 if future_return > threshold else 0.
        Preserves NaN where future return is unobserved.
        """
        out = df.copy()
        ret_col = target_return_col or f"target_return_{horizon}d"
        if ret_col not in out.columns:
            out = TargetGenerator.add_forward_returns(out, horizons=[horizon])

        col_binary = f"target_binary_{horizon}d"
        valid_mask = out[ret_col].notna()
        out[col_binary] = np.nan
        out.loc[valid_mask, col_binary] = (out.loc[valid_mask, ret_col] > threshold).astype(float)
        return out
