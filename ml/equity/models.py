"""
ml/equity/models.py — Tabular Model Implementations and Preprocessing Pipelines.

Provides:
  1. IEquityModel: Abstract base class for all equity models
  2. NaiveBaselineModel: Historical training mean / zero-return baseline
  3. LinearEquityModel: Ridge regression with training-only StandardScaler
  4. TreeEquityModel: RandomForestRegressor with deterministic seeds and feature importances

STRICT PREPROCESSING ISOLATION:
  All scalers and imputers are fitted ONLY on training features (X_train).
  Validation and test sets use the frozen training transformations.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


class IEquityModel(ABC):
    """Abstract interface for all equity forecasting models."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def fit(self, X: pd.DataFrame, y: pd.Series) -> None:
        """Fit model and internal preprocessors strictly on training data."""
        raise NotImplementedError

    @abstractmethod
    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """Generate point forecasts for return target."""
        raise NotImplementedError

    @abstractmethod
    def get_feature_importance(self) -> Dict[str, float]:
        """Return feature importance or normalized coefficients."""
        raise NotImplementedError


class NaiveBaselineModel(IEquityModel):
    """
    Naive baseline model.
    
    Predicts constant historical training mean return (or constant 0.0).
    """

    def __init__(self, strategy: str = "mean"):
        self.strategy = strategy
        self._mean_val: float = 0.0
        self._feature_names: List[str] = []

    @property
    def model_name(self) -> str:
        return f"Naive_{self.strategy}"

    def fit(self, X: pd.DataFrame, y: pd.Series) -> None:
        self._feature_names = list(X.columns)
        if self.strategy == "zero":
            self._mean_val = 0.0
        else:
            self._mean_val = float(y.mean()) if len(y) > 0 else 0.0

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return np.full(len(X), self._mean_val, dtype=float)

    def get_feature_importance(self) -> Dict[str, float]:
        return {f: 0.0 for f in self._feature_names}


class LinearEquityModel(IEquityModel):
    """
    Linear Ridge regression baseline with training-only imputation and standardization.
    """

    def __init__(self, alpha: float = 1.0, fit_intercept: bool = True):
        self.alpha = alpha
        self.fit_intercept = fit_intercept
        self.pipeline: Optional[Pipeline] = None
        self._feature_names: List[str] = []

    @property
    def model_name(self) -> str:
        return f"Ridge(alpha={self.alpha})"

    def fit(self, X: pd.DataFrame, y: pd.Series) -> None:
        self._feature_names = list(X.columns)
        self.pipeline = Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            ("regressor", Ridge(alpha=self.alpha, fit_intercept=self.fit_intercept)),
        ])
        self.pipeline.fit(X, y)

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        if self.pipeline is None:
            raise RuntimeError("Model must be fitted before calling predict().")
        return self.pipeline.predict(X)

    def get_feature_importance(self) -> Dict[str, float]:
        if self.pipeline is None:
            return {}
        reg = self.pipeline.named_steps["regressor"]
        coefs = reg.coef_
        # Absolute normalized coefficients
        abs_coefs = np.abs(coefs)
        total = np.sum(abs_coefs) + 1e-12
        norm_coefs = abs_coefs / total
        return {feat: float(norm_coefs[i]) for i, feat in enumerate(self._feature_names)}


class TreeEquityModel(IEquityModel):
    """
    RandomForest tabular model with deterministic random seed and bounded depth.
    """

    def __init__(
        self,
        n_estimators: int = 100,
        max_depth: int = 6,
        min_samples_leaf: int = 20,
        random_state: int = 42,
    ):
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.min_samples_leaf = min_samples_leaf
        self.random_state = random_state
        self.pipeline: Optional[Pipeline] = None
        self._feature_names: List[str] = []

    @property
    def model_name(self) -> str:
        return f"RandomForest(n={self.n_estimators}, depth={self.max_depth})"

    def fit(self, X: pd.DataFrame, y: pd.Series) -> None:
        self._feature_names = list(X.columns)
        rf = RandomForestRegressor(
            n_estimators=self.n_estimators,
            max_depth=self.max_depth,
            min_samples_leaf=self.min_samples_leaf,
            random_state=self.random_state,
            n_jobs=-1,
        )
        self.pipeline = Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("regressor", rf),
        ])
        self.pipeline.fit(X, y)

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        if self.pipeline is None:
            raise RuntimeError("Model must be fitted before calling predict().")
        return self.pipeline.predict(X)

    def get_feature_importance(self) -> Dict[str, float]:
        if self.pipeline is None:
            return {}
        reg = self.pipeline.named_steps["regressor"]
        importances = reg.feature_importances_
        return {feat: float(importances[i]) for i, feat in enumerate(self._feature_names)}
