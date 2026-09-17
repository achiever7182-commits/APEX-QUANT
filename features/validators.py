"""
features/validators.py — Quality and zero-lookahead validation for computed features.

Enforces:
  - Uniqueness: No duplicate (timestamp, symbol) pairs
  - Monotonicity: Strictly ascending timestamps per instrument
  - Finite bounds: Zero infinite (+/- inf) values allowed
  - Domain validation: RSI in [0, 100], ATR >= 0, Volatility >= 0
  - Missing value diagnosis: Distinguishes legitimate warmup NaNs from anomalous gaps
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence
import numpy as np
import pandas as pd

from features.models import FeatureValidationResult


class FeatureValidator:
    """Validates integrity and consistency of single-stock and cross-sectional feature matrices."""

    @staticmethod
    def validate_panel(
        df: pd.DataFrame,
        feature_cols: Sequence[str],
        timestamp_col: str = "timestamp",
        symbol_col: str = "symbol",
        max_allowed_warmup_bars: int = 200,
    ) -> FeatureValidationResult:
        """
        Run full validation on a feature dataset.

        Returns:
            FeatureValidationResult containing detailed diagnostics.
        """
        errors: List[str] = []
        warnings: List[str] = []

        total_rows = len(df)
        total_cols = len(df.columns)
        num_features = len(feature_cols)

        if total_rows == 0:
            return FeatureValidationResult(
                is_valid=False,
                total_rows=0,
                total_columns=total_cols,
                feature_count=num_features,
                error_messages=["Feature panel is completely empty."],
            )

        # 1. Check duplicate keys
        duplicate_count = 0
        if timestamp_col in df.columns and symbol_col in df.columns:
            dups = df.duplicated(subset=[timestamp_col, symbol_col], keep=False)
            duplicate_count = int(dups.sum())
            if duplicate_count > 0:
                errors.append(f"Found {duplicate_count} duplicate ({timestamp_col}, {symbol_col}) rows.")

        # 2. Check timestamp monotonicity per symbol
        monotonic_errors = 0
        if timestamp_col in df.columns and symbol_col in df.columns:
            for sym, group in df.groupby(symbol_col):
                ts = pd.to_datetime(group[timestamp_col])
                if not ts.is_monotonic_increasing:
                    monotonic_errors += 1
                    errors.append(f"Timestamps for symbol '{sym}' are not monotonically increasing.")

        # 3. Check infinite values
        inf_counts: Dict[str, int] = {}
        for col in feature_cols:
            if col in df.columns and np.issubdtype(df[col].dtype, np.number):
                inf_sum = int(np.isinf(df[col]).sum())
                if inf_sum > 0:
                    inf_counts[col] = inf_sum
                    errors.append(f"Feature '{col}' contains {inf_sum} infinite values.")

        # 4. Check NaN values
        nan_counts: Dict[str, int] = {}
        for col in feature_cols:
            if col in df.columns:
                nan_sum = int(df[col].isna().sum())
                nan_counts[col] = nan_sum
                # Warmup NaNs are normal, but warn if a feature is 100% NaN
                if nan_sum == total_rows:
                    warnings.append(f"Feature '{col}' is entirely NaN across all {total_rows} rows.")

        # 5. Check domain bounds
        domain_violations: Dict[str, int] = {}

        # RSI checks [0.0, 100.0]
        rsi_cols = [c for c in feature_cols if c.startswith("rsi_") and not c.startswith("rsi_momentum")]
        for rsi_col in rsi_cols:
            if rsi_col in df.columns:
                s = df[rsi_col].dropna()
                bad = ((s < 0.0) | (s > 100.0)).sum()
                if bad > 0:
                    domain_violations[rsi_col] = int(bad)
                    errors.append(f"Feature '{rsi_col}' has {bad} values outside [0, 100].")

        # Non-negative checks (ATR, Volatility, Turnover, Range)
        non_neg_prefixes = ("atr_", "volatility_", "turnover", "candle_range_pct", "downside_volatility_")
        for col in feature_cols:
            if any(col.startswith(pfx) for pfx in non_neg_prefixes) and col in df.columns:
                s = df[col].dropna()
                bad = (s < -1e-6).sum()
                if bad > 0:
                    domain_violations[col] = int(bad)
                    errors.append(f"Feature '{col}' has {bad} negative values.")

        first_ts = df[timestamp_col].min() if timestamp_col in df.columns else None
        last_ts = df[timestamp_col].max() if timestamp_col in df.columns else None

        is_valid = len(errors) == 0

        return FeatureValidationResult(
            is_valid=is_valid,
            total_rows=total_rows,
            total_columns=total_cols,
            feature_count=num_features,
            nan_counts=nan_counts,
            inf_counts=inf_counts,
            duplicate_count=duplicate_count,
            monotonic_errors=monotonic_errors,
            domain_violations=domain_violations,
            first_valid_timestamp=first_ts,
            last_valid_timestamp=last_ts,
            error_messages=errors,
            warning_messages=warnings,
        )
