"""
ml/equity/split.py — Chronological and Walk-Forward Dataset Splitting.

Enforces:
  1. Strict Chronological Ordering:
     max(Train Dates) < min(Validation Dates) < min(Test Dates)
  2. Multi-Stock Synchronization:
     All instruments are partitioned at identical time boundaries.
  3. Zero Random Shuffling:
     Prevents future market regimes from leaking into earlier training samples.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generator, List, Optional, Tuple, Union
import pandas as pd


@dataclass
class DatasetSplit:
    """Container for chronologically partitioned datasets and boundary timestamps."""
    train_df: pd.DataFrame
    val_df: pd.DataFrame
    test_df: pd.DataFrame
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    val_start: pd.Timestamp
    val_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp

    @property
    def train_rows(self) -> int:
        return len(self.train_df)

    @property
    def val_rows(self) -> int:
        return len(self.val_df)

    @property
    def test_rows(self) -> int:
        return len(self.test_df)


class ChronologicalSplitter:
    """Partitions tabular panel data chronologically."""

    @staticmethod
    def split(
        df: pd.DataFrame,
        train_ratio: float = 0.70,
        val_ratio: float = 0.15,
        test_ratio: float = 0.15,
        timestamp_col: str = "timestamp",
    ) -> DatasetSplit:
        """
        Split a multi-stock panel chronologically by unique dates.

        Parameters:
            df: Input panel DataFrame.
            train_ratio, val_ratio, test_ratio: Ratios summing to 1.0.
            timestamp_col: Name of timestamp column.
        """
        if abs((train_ratio + val_ratio + test_ratio) - 1.0) > 1e-6:
            raise ValueError("train_ratio, val_ratio, and test_ratio must sum to 1.0.")

        clean = df.copy()
        clean[timestamp_col] = pd.to_datetime(clean[timestamp_col])
        clean = clean.sort_values(by=timestamp_col).reset_index(drop=True)

        unique_dates = sorted(list(clean[timestamp_col].unique()))
        n_dates = len(unique_dates)
        if n_dates < 10:
            raise ValueError(f"Dataset has too few unique dates ({n_dates}) for chronological splitting.")

        train_idx = int(n_dates * train_ratio)
        val_idx = int(n_dates * (train_ratio + val_ratio))

        train_cutoff = unique_dates[train_idx]
        val_cutoff = unique_dates[val_idx]

        train_df = clean[clean[timestamp_col] < train_cutoff].reset_index(drop=True)
        val_df = clean[(clean[timestamp_col] >= train_cutoff) & (clean[timestamp_col] < val_cutoff)].reset_index(drop=True)
        test_df = clean[clean[timestamp_col] >= val_cutoff].reset_index(drop=True)

        return DatasetSplit(
            train_df=train_df,
            val_df=val_df,
            test_df=test_df,
            train_start=train_df[timestamp_col].min(),
            train_end=train_df[timestamp_col].max(),
            val_start=val_df[timestamp_col].min(),
            val_end=val_df[timestamp_col].max(),
            test_start=test_df[timestamp_col].min(),
            test_end=test_df[timestamp_col].max(),
        )

    @staticmethod
    def split_by_dates(
        df: pd.DataFrame,
        val_start_date: Union[str, pd.Timestamp],
        test_start_date: Union[str, pd.Timestamp],
        timestamp_col: str = "timestamp",
    ) -> DatasetSplit:
        """
        Split a multi-stock panel using explicit calendar dates.
        """
        clean = df.copy()
        clean[timestamp_col] = pd.to_datetime(clean[timestamp_col])
        val_dt = pd.to_datetime(val_start_date)
        test_dt = pd.to_datetime(test_start_date)

        if val_dt >= test_dt:
            raise ValueError("val_start_date must be strictly before test_start_date.")

        # Ensure tz-awareness compatibility
        ts_tz = clean[timestamp_col].dt.tz
        if ts_tz is not None:
            if val_dt.tzinfo is None:
                val_dt = val_dt.tz_localize(ts_tz)
            if test_dt.tzinfo is None:
                test_dt = test_dt.tz_localize(ts_tz)
        else:
            if val_dt.tzinfo is not None:
                val_dt = val_dt.tz_localize(None)
            if test_dt.tzinfo is not None:
                test_dt = test_dt.tz_localize(None)

        train_df = clean[clean[timestamp_col] < val_dt].reset_index(drop=True)
        val_df = clean[(clean[timestamp_col] >= val_dt) & (clean[timestamp_col] < test_dt)].reset_index(drop=True)
        test_df = clean[clean[timestamp_col] >= test_dt].reset_index(drop=True)

        return DatasetSplit(
            train_df=train_df,
            val_df=val_df,
            test_df=test_df,
            train_start=train_df[timestamp_col].min(),
            train_end=train_df[timestamp_col].max(),
            val_start=val_df[timestamp_col].min(),
            val_end=val_df[timestamp_col].max(),
            test_start=test_df[timestamp_col].min(),
            test_end=test_df[timestamp_col].max(),
        )


class WalkForwardSplitter:
    """
    Generates expanding-window walk-forward splits for robust chronological validation.
    """

    @staticmethod
    def generate_folds(
        df: pd.DataFrame,
        n_folds: int = 3,
        val_ratio: float = 0.2,
        timestamp_col: str = "timestamp",
    ) -> Generator[Tuple[pd.DataFrame, pd.DataFrame, int], None, None]:
        """
        Generate expanding-window training and validation folds.
        
        Yields:
            (train_fold_df, val_fold_df, fold_index)
        """
        clean = df.copy()
        clean[timestamp_col] = pd.to_datetime(clean[timestamp_col])
        clean = clean.sort_values(by=timestamp_col).reset_index(drop=True)

        unique_dates = sorted(list(clean[timestamp_col].unique()))
        total_dates = len(unique_dates)
        val_window_size = int(total_dates * val_ratio / n_folds)

        if val_window_size < 5:
            raise ValueError("Too few dates per fold in walk-forward splitter.")

        min_train_size = total_dates - (val_window_size * n_folds)

        for fold in range(n_folds):
            train_end_idx = min_train_size + (fold * val_window_size)
            val_end_idx = train_end_idx + val_window_size

            train_cutoff = unique_dates[train_end_idx]
            val_cutoff = unique_dates[min(val_end_idx, total_dates - 1)]

            train_fold = clean[clean[timestamp_col] < train_cutoff].reset_index(drop=True)
            val_fold = clean[
                (clean[timestamp_col] >= train_cutoff) & (clean[timestamp_col] <= val_cutoff)
            ].reset_index(drop=True)

            yield train_fold, val_fold, fold + 1
