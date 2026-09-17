"""
ml/equity/dataset.py — ML Dataset Builder with Point-in-Time Universe Alignment.

Assembles:
  Market Data (Parquet)
       ↓
  Features (Step 4 FeatureEngine)
       ↓
  Targets (ml/equity/targets.py)
       ↓
  Point-in-Time Universe Filter (Step 3 UniverseManager / Nifty500)
       ↓
  EquityMLDataset [timestamp, symbol, X_features, Y_target]

SURVIVORSHIP BIAS PROTECTION:
  Rows for symbol S at date T are only included if S was a verified member
  of the universe on date T. Stocks added in the future cannot be trained on
  during dates prior to their index inclusion.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Dict, List, Optional, Sequence, Tuple, Union
import numpy as np
import pandas as pd

from features.engine import FeatureEngine
from features.models import FeatureConfig, FeatureSet
from ml.equity.targets import TargetGenerator
from universe.nifty500 import Nifty500
from universe.universe_manager import UniverseManager

logger = logging.getLogger("apex_quant.ml.equity")


@dataclass
class EquityMLDataset:
    """Standard container for equity machine learning datasets."""
    data: pd.DataFrame
    feature_names: List[str]
    target_name: str
    symbols: List[str]
    start_date: pd.Timestamp
    end_date: pd.Timestamp

    @property
    def row_count(self) -> int:
        return len(self.data)

    @property
    def feature_count(self) -> int:
        return len(self.feature_names)

    def get_X_y(self) -> Tuple[pd.DataFrame, pd.Series]:
        """Return features matrix X and target vector y."""
        X = self.data[self.feature_names].copy()
        y = self.data[self.target_name].copy()
        return X, y


class EquityMLDatasetBuilder:
    """
    Constructs clean, zero-lookahead, survivorship-bias-free ML datasets.
    """

    def __init__(
        self,
        feature_engine: Optional[FeatureEngine] = None,
        universe_manager: Optional[UniverseManager] = None,
        target_horizon: int = 5,
    ):
        self.feature_engine = feature_engine or FeatureEngine()
        self.universe_manager = universe_manager or UniverseManager()
        self.target_horizon = target_horizon

    def build_dataset_from_feature_set(
        self,
        feature_set: FeatureSet,
        raw_or_adj_dfs: Dict[str, pd.DataFrame],
        target_horizon: Optional[int] = None,
        filter_pit_universe: bool = True,
        min_history_filter: bool = True,
        drop_target_na: bool = True,
    ) -> EquityMLDataset:
        """
        Combine computed features with forward targets and apply Point-in-Time universe filtering.

        Parameters:
            feature_set: Step 4 FeatureSet containing computed multi-stock features.
            raw_or_adj_dfs: Dict of symbol -> DataFrame containing 'close' for forward return calculation.
            target_horizon: Forward horizon (default: self.target_horizon, e.g. 5 days).
            filter_pit_universe: If True, drops rows where stock was not active on that date.
            min_history_filter: If True, drops warmup rows where has_sufficient_history == False.
            drop_target_na: If True, drops rows with unobserved target (e.g. final k bars of dataset).
        """
        horizon = target_horizon or self.target_horizon
        panel = feature_set.data.copy()
        if panel.empty:
            raise ValueError("Cannot build ML dataset from an empty FeatureSet.")

        target_col = f"target_return_{horizon}d"

        # 1. Attach close prices to calculate forward targets if not already in panel
        if "close" not in panel.columns:
            close_map_dfs = []
            for sym, df in raw_or_adj_dfs.items():
                df_c = df[["timestamp", "close"]].copy()
                df_c["timestamp"] = pd.to_datetime(df_c["timestamp"])
                df_c["symbol"] = sym
                close_map_dfs.append(df_c)
            if close_map_dfs:
                close_df = pd.concat(close_map_dfs, ignore_index=True)
                panel = pd.merge(panel, close_df, on=["timestamp", "symbol"], how="left")

        # 2. Generate forward-looking return targets
        panel = TargetGenerator.add_forward_returns(
            panel,
            horizons=[horizon],
            close_col="close",
            symbol_col="symbol",
            timestamp_col="timestamp",
        )

        # 3. Point-in-Time Universe filtering (Survivorship-Bias Protection)
        if filter_pit_universe and self.universe_manager is not None:
            nifty = self.universe_manager.nifty500
            initial_count = len(panel)
            valid_pit_mask = []
            for _, row in panel.iterrows():
                row_date = pd.to_datetime(row["timestamp"]).date()
                sym = row["symbol"]
                # Check if symbol was an active constituent on row_date
                snap = nifty.get_point_in_time_constituents(row_date)
                valid_pit_mask.append(sym in snap.symbols)

            panel = panel[valid_pit_mask].reset_index(drop=True)
            logger.info(
                f"Point-in-Time universe filter applied: retained {len(panel)} of {initial_count} rows."
            )

        # 4. Filter warmup periods
        if min_history_filter and "has_sufficient_history" in panel.columns:
            panel = panel[panel["has_sufficient_history"] == True].reset_index(drop=True)

        # 5. Drop unobserved targets (tail rows)
        if drop_target_na:
            panel = panel[panel[target_col].notna()].reset_index(drop=True)

        # 6. Ensure no infinite values in feature columns
        feature_names = [f for f in feature_set.feature_columns if f in panel.columns]
        for col in feature_names:
            if np.issubdtype(panel[col].dtype, np.number):
                panel = panel[~np.isinf(panel[col])]

        panel = panel.sort_values(by=["timestamp", "symbol"]).reset_index(drop=True)

        return EquityMLDataset(
            data=panel,
            feature_names=feature_names,
            target_name=target_col,
            symbols=sorted(list(panel["symbol"].unique())),
            start_date=panel["timestamp"].min(),
            end_date=panel["timestamp"].max(),
        )
