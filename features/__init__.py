"""
features — APEX QUANT Multi-Stock Feature Engineering Subsystem.

Provides zero-lookahead, point-in-time safe feature extraction for Indian equities:
  - Price returns & price dynamics
  - Trend moving averages (SMA, EMA, ratios, spreads)
  - Momentum & oscillators (RSI, ROC, normalized momentum)
  - Volatility & risk metrics (rolling std, ATR, ATR %, downside volatility)
  - Volume & turnover dynamics
  - Relative strength vs configurable benchmarks
  - Market regime indicators
  - Cross-sectional normalization (Z-score, Rank, Winsorize)
  - Data quality validation & leakage prevention
"""

from features.models import (
    FeatureCategory,
    FeatureConfig,
    FeatureMetadata,
    FeatureSet,
    FeatureValidationResult,
)
from features.price import (
    PRICE_FEATURE_METADATA,
    calculate_price_features,
)
from features.trend import (
    TREND_FEATURE_METADATA,
    calculate_trend_features,
)
from features.momentum import (
    MOMENTUM_FEATURE_METADATA,
    calculate_momentum_features,
    calculate_rsi,
)
from features.volatility import (
    VOLATILITY_FEATURE_METADATA,
    calculate_atr,
    calculate_volatility_features,
)
from features.volume import (
    VOLUME_FEATURE_METADATA,
    calculate_volume_features,
)
from features.relative_strength import (
    RELATIVE_STRENGTH_FEATURE_METADATA,
    BenchmarkProvider,
    calculate_relative_strength_features,
)
from features.market_regime import (
    REGIME_FEATURE_METADATA,
    calculate_market_regime_features,
)
from features.normalization import (
    cross_sectional_rank,
    cross_sectional_winsorize,
    cross_sectional_zscore,
)
from features.validators import FeatureValidator
from features.engine import FeatureEngine

__all__ = [
    "FeatureCategory",
    "FeatureConfig",
    "FeatureMetadata",
    "FeatureSet",
    "FeatureValidationResult",
    "FeatureEngine",
    "FeatureValidator",
    "BenchmarkProvider",
    "calculate_price_features",
    "calculate_trend_features",
    "calculate_momentum_features",
    "calculate_rsi",
    "calculate_volatility_features",
    "calculate_atr",
    "calculate_volume_features",
    "calculate_relative_strength_features",
    "calculate_market_regime_features",
    "cross_sectional_zscore",
    "cross_sectional_rank",
    "cross_sectional_winsorize",
]
