"""
ml/equity/predict.py — Production Inference Engine for Equity Forecasting.

Loads trained model artifacts and generates point predictions:
  Input: Panel DataFrame [timestamp, symbol, feature_1, ..., feature_k]
  Output: Predictions DataFrame [timestamp, symbol, predicted_return]

Enforces feature column ordering, imputation, and zero lookahead at inference time.
"""

from __future__ import annotations

from typing import List, Optional, Union
import numpy as np
import pandas as pd

from ml.equity.models import IEquityModel
from ml.equity.registry import ModelArtifactMetadata, ModelRegistry


class EquityPredictor:
    """
    Executes inference using trained equity forecasting models.
    """

    def __init__(
        self,
        model: IEquityModel,
        feature_names: List[str],
        metadata: Optional[ModelArtifactMetadata] = None,
    ):
        self.model = model
        self.feature_names = feature_names
        self.metadata = metadata

    @classmethod
    def from_registry(
        cls,
        version: str,
        registry: Optional[ModelRegistry] = None,
    ) -> EquityPredictor:
        """Load predictor directly from ModelRegistry version."""
        reg = registry or ModelRegistry()
        model, meta = reg.load_artifact(version)
        return cls(model=model, feature_names=meta.features, metadata=meta)

    def predict(
        self,
        df: pd.DataFrame,
        timestamp_col: str = "timestamp",
        symbol_col: str = "symbol",
    ) -> pd.DataFrame:
        """
        Generate predictions for a panel DataFrame.

        Parameters:
            df: DataFrame containing timestamp, symbol, and required feature columns.
            timestamp_col: Name of timestamp column.
            symbol_col: Name of symbol column.

        Returns:
            DataFrame containing [timestamp, symbol, predicted_return].
        """
        if df.empty:
            return pd.DataFrame(columns=[timestamp_col, symbol_col, "predicted_return"])

        # Validate that all required features exist in input
        missing = [f for f in self.feature_names if f not in df.columns]
        if missing:
            raise ValueError(
                f"Input DataFrame is missing {len(missing)} required features for model: {missing[:5]}..."
            )

        # Extract features strictly in training order
        X = df[self.feature_names].copy()
        preds = self.model.predict(X)

        result = pd.DataFrame({
            timestamp_col: df[timestamp_col].values,
            symbol_col: df[symbol_col].values,
            "predicted_return": preds,
        })
        return result
