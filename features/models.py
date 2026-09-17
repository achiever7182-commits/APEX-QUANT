"""
features/models.py — Data models and configurations for APEX QUANT Feature Engineering.

Defines:
  - FeatureConfig: Centralized lookback windows, calculation settings, and benchmark options
  - FeatureCategory: Enumeration of feature types
  - FeatureMetadata: Metadata descriptor for each registered feature
  - FeatureSet: Container for computed feature matrices and diagnostics
  - FeatureValidationResult: Result of data quality and zero-lookahead validation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence
import pandas as pd


class FeatureCategory(str, Enum):
    PRICE = "price"
    TREND = "trend"
    MOMENTUM = "momentum"
    VOLATILITY = "volatility"
    VOLUME = "volume"
    RELATIVE_STRENGTH = "relative_strength"
    MARKET_REGIME = "market_regime"
    CROSS_SECTIONAL = "cross_sectional"


@dataclass(frozen=True)
class FeatureMetadata:
    """Metadata descriptor for a single feature."""
    name: str
    category: FeatureCategory
    lookback_bars: int
    description: str
    requires_adjusted: bool = True
    is_bounded: bool = False
    lower_bound: Optional[float] = None
    upper_bound: Optional[float] = None


@dataclass
class FeatureConfig:
    """
    Central configuration for APEX QUANT multi-stock feature calculation.
    
    All periods and lookbacks are defined here and can be overridden per experiment.
    """
    # Price returns lookbacks (in daily bars)
    return_periods: List[int] = field(default_factory=lambda: [1, 3, 5, 10, 20, 60])
    
    # Trend moving averages
    sma_periods: List[int] = field(default_factory=lambda: [5, 10, 20, 50, 100, 200])
    ema_periods: List[int] = field(default_factory=lambda: [9, 21, 50])
    
    # Momentum lookbacks
    rsi_period: int = 14
    roc_periods: List[int] = field(default_factory=lambda: [5, 10, 20, 60])
    mom_periods: List[int] = field(default_factory=lambda: [5, 10, 20, 60])
    
    # Volatility / risk lookbacks
    volatility_periods: List[int] = field(default_factory=lambda: [10, 20, 60])
    atr_period: int = 14
    downside_vol_period: int = 20
    
    # Volume lookbacks
    volume_sma_periods: List[int] = field(default_factory=lambda: [10, 20])
    volume_momentum_period: int = 5
    
    # Relative strength vs benchmark
    relative_return_periods: List[int] = field(default_factory=lambda: [5, 20, 60])
    benchmark_symbol: Optional[str] = None  # If None, synthetic composite from benchmark basket is used
    benchmark_basket: List[str] = field(
        default_factory=lambda: ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]
    )
    
    # Market regime settings
    regime_sma_fast: int = 50
    regime_sma_slow: int = 200
    regime_return_period: int = 20
    regime_volatility_period: int = 20
    
    # Normalization & quality thresholds
    winsorize_limits: tuple = (0.01, 0.01)
    min_history_bars: int = 60  # Minimum bars for has_sufficient_history flag
    full_warmup_bars: int = 200 # Max lookback required for all features (e.g. SMA 200)

    def max_lookback(self) -> int:
        """Return the maximum lookback window across all configured features."""
        candidates = (
            self.return_periods
            + self.sma_periods
            + self.ema_periods
            + [self.rsi_period]
            + self.roc_periods
            + self.mom_periods
            + self.volatility_periods
            + [self.atr_period, self.downside_vol_period]
            + self.volume_sma_periods
            + [self.volume_momentum_period]
            + self.relative_return_periods
            + [self.regime_sma_fast, self.regime_sma_slow]
        )
        return max(candidates) if candidates else 200


@dataclass
class FeatureValidationResult:
    """Diagnostic report from FeatureValidator."""
    is_valid: bool
    total_rows: int
    total_columns: int
    feature_count: int
    nan_counts: Dict[str, int] = field(default_factory=dict)
    inf_counts: Dict[str, int] = field(default_factory=dict)
    duplicate_count: int = 0
    monotonic_errors: int = 0
    domain_violations: Dict[str, int] = field(default_factory=dict)
    first_valid_timestamp: Optional[Any] = None
    last_valid_timestamp: Optional[Any] = None
    error_messages: List[str] = field(default_factory=list)
    warning_messages: List[str] = field(default_factory=list)


@dataclass
class FeatureSet:
    """Container for computed features dataframe along with metadata and diagnostics."""
    data: pd.DataFrame
    config: FeatureConfig
    feature_columns: List[str]
    symbols: List[str]
    validation_result: Optional[FeatureValidationResult] = None
    is_normalized: bool = False

    @property
    def row_count(self) -> int:
        return len(self.data)

    @property
    def feature_count(self) -> int:
        return len(self.feature_columns)
