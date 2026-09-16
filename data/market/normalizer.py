"""
data/market/normalizer.py — Data Normalization and Cleaning Engine for APEX QUANT.

Standardizes raw market data streams into canonical schema, enforces numeric types,
verifies mathematical OHLC consistency, and deduplicates chronological records.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class DataNormalizer:
    """
    Cleans, normalizes, and validates tabular market data into canonical internal format.
    
    Guarantees:
    - Column names match ['timestamp', 'open', 'high', 'low', 'close', 'volume']
    - Timestamp is strictly ascending datetime64
    - No duplicate timestamps
    - Valid OHLC relationships (high >= open/close, low <= open/close, high >= low)
    - Non-negative volume and prices
    - Explicit logging of any dropped or corrected rows
    """

    COLUMN_MAP = {
        "date": "timestamp",
        "datetime": "timestamp",
        "time": "timestamp",
        "timestamp": "timestamp",
        "open": "open",
        "high": "high",
        "low": "low",
        "close": "close",
        "adj close": "adjusted_close",
        "adj_close": "adjusted_close",
        "adjusted_close": "adjusted_close",
        "volume": "volume",
        "vol": "volume",
        "turnover": "turnover",
        "vwap": "vwap",
    }

    @classmethod
    def normalize_symbol(cls, symbol: str) -> str:
        """Strip exchange suffixes (.NS, .BO) and whitespace, returning canonical uppercase symbol."""
        if not symbol:
            raise ValueError("Symbol cannot be empty.")
        clean = symbol.upper().strip()
        for suffix in [".NS", ".BO", ".BSE", ".NSE"]:
            if clean.endswith(suffix):
                clean = clean[:-len(suffix)]
        return clean.strip()

    @classmethod
    def normalize(
        cls,
        df: pd.DataFrame,
        symbol: Optional[str] = None,
        drop_invalid: bool = True,
    ) -> Tuple[pd.DataFrame, List[str]]:
        """
        Normalize and clean raw OHLCV DataFrame.
        
        Args:
            df: Raw input DataFrame
            symbol: Optional ticker symbol for logging context
            drop_invalid: If True, drop unrecoverable rows violating OHLC constraints
            
        Returns:
            Tuple of (cleaned_df, list_of_audit_log_messages)
        """
        logs: List[str] = []
        sym_tag = f"[{cls.normalize_symbol(symbol)}] " if symbol else ""

        if df.empty:
            logs.append(f"{sym_tag}Warning: Input DataFrame is empty.")
            canonical_cols = ["timestamp", "open", "high", "low", "close", "volume"]
            return pd.DataFrame(columns=canonical_cols), logs

        out = df.copy()

        # 1. Standardize column names (lowercase and strip)
        rename_dict = {}
        for col in out.columns:
            cleaned_col = str(col).lower().strip()
            if cleaned_col in cls.COLUMN_MAP:
                rename_dict[col] = cls.COLUMN_MAP[cleaned_col]
        out = out.rename(columns=rename_dict)

        required_cols = ["timestamp", "open", "high", "low", "close", "volume"]
        missing_req = [c for c in required_cols if c not in out.columns]
        if missing_req:
            err = f"{sym_tag}Fatal: Missing required columns: {missing_req}"
            logs.append(err)
            raise ValueError(err)

        # 2. Normalize timestamps to datetime64 and timezone-unaware UTC for Parquet standard
        try:
            out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True)
        except Exception as e:
            err = f"{sym_tag}Failed to parse timestamps: {e}"
            logs.append(err)
            raise ValueError(err)

        # 3. Enforce numeric types
        numeric_cols = ["open", "high", "low", "close", "volume"]
        for col in numeric_cols:
            out[col] = pd.to_numeric(out[col], errors="coerce")

        # 4. Remove rows with NaN in critical columns
        nan_mask = out[numeric_cols].isna().any(axis=1) | out["timestamp"].isna()
        nan_count = int(nan_mask.sum())
        if nan_count > 0:
            logs.append(f"{sym_tag}Dropped {nan_count} rows containing NaN/null values in required fields.")
            out = out[~nan_mask].copy()

        # 5. Deduplicate timestamps
        init_len = len(out)
        out = out.sort_values("timestamp").reset_index(drop=True)
        dup_mask = out.duplicated(subset=["timestamp"], keep="last")
        dup_count = int(dup_mask.sum())
        if dup_count > 0:
            logs.append(f"{sym_tag}Deduplicated {dup_count} duplicate timestamps (kept latest record).")
            out = out[~dup_mask].reset_index(drop=True)

        # 6. Check and enforce OHLC logical constraints
        # Constraint a: Negative values
        neg_price_mask = (out["open"] < 0) | (out["high"] < 0) | (out["low"] < 0) | (out["close"] < 0)
        neg_price_count = int(neg_price_mask.sum())
        if neg_price_count > 0:
            logs.append(f"{sym_tag}Found {neg_price_count} rows with negative prices.")
            if drop_invalid:
                out = out[~neg_price_mask].copy()

        neg_vol_mask = out["volume"] < 0
        neg_vol_count = int(neg_vol_mask.sum())
        if neg_vol_count > 0:
            logs.append(f"{sym_tag}Found {neg_vol_count} rows with negative volume.")
            if drop_invalid:
                out = out[~neg_vol_mask].copy()

        # Constraint b: high >= low
        hl_inv_mask = out["high"] < out["low"]
        hl_inv_count = int(hl_inv_mask.sum())
        if hl_inv_count > 0:
            logs.append(f"{sym_tag}Found {hl_inv_count} rows where high < low.")
            if drop_invalid:
                out = out[~hl_inv_mask].copy()

        # Constraint c: high >= max(open, close) and low <= min(open, close)
        # Minor float tolerance (1e-4) for floating point precision issues
        tol = 1e-4
        max_oc = np.maximum(out["open"], out["close"])
        min_oc = np.minimum(out["open"], out["close"])

        high_viol = out["high"] < (max_oc - tol)
        low_viol = out["low"] > (min_oc + tol)

        viol_mask = high_viol | low_viol
        viol_count = int(viol_mask.sum())
        if viol_count > 0:
            logs.append(f"{sym_tag}Found {viol_count} rows where open/close was outside [low, high] bounds.")
            if drop_invalid:
                out = out[~viol_mask].copy()
            else:
                # Sanitize high/low to encompass open/close
                out["high"] = np.maximum(out["high"], max_oc)
                out["low"] = np.minimum(out["low"], min_oc)
                logs.append(f"{sym_tag}Adjusted bounds to encompass open/close.")

        out = out.sort_values("timestamp").reset_index(drop=True)
        logs.append(f"{sym_tag}Normalization complete. Clean rows: {len(out)} (original: {init_len}).")
        return out, logs
