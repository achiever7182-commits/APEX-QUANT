"""
ranking/config.py — Configuration and Weight Architecture for Stock Ranking.

Defines:
  - RankingConfig: Weights, normalization modes, thresholds, and Top-K settings
  - Default baseline weights for Composite Opportunity Score
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional


DEFAULT_RANKING_WEIGHTS: Dict[str, float] = {
    "prediction": 0.35,        # Raw forward return expectation
    "risk_adjusted": 0.20,     # Return normalized by rolling return volatility
    "relative_strength": 0.15, # Outperformance vs synthetic equal-weighted benchmark (not official NIFTY 500 index)
    "momentum": 0.10,          # RSI, ROC, normalized price momentum
    "trend": 0.10,             # Moving average spreads and price-to-SMA ratios
    "market_regime": 0.05,     # Macro trend and benchmark volatility state (from synthetic benchmark)
    "liquidity": 0.05,         # Trading volume and turnover consistency
}


@dataclass
class RankingConfig:
    """
    Configuration dataclass for the Cross-Sectional Ranking Engine.
    
    All weights and thresholds are explicit and configurable.
    """
    weights: Dict[str, float] = field(default_factory=lambda: dict(DEFAULT_RANKING_WEIGHTS))
    normalization_method: str = "percentile"  # 'percentile' (maps to [0, 1]) or 'zscore'
    min_predicted_return: Optional[float] = None
    min_opportunity_score: Optional[float] = None
    min_median_turnover: Optional[float] = None
    max_volatility: Optional[float] = None
    top_k: Optional[int] = None  # If set, limits output to top K eligible opportunities
    tie_breaker: str = "standard"  # 1. opportunity_score desc, 2. predicted_return desc, 3. symbol asc

    def __post_init__(self) -> None:
        total_w = sum(self.weights.values())
        if abs(total_w - 1.0) > 1e-4:
            raise ValueError(f"Ranking weights must sum to 1.0 (current sum: {total_w:.4f})")
        if self.normalization_method not in ("percentile", "zscore"):
            raise ValueError(f"Unknown normalization_method: {self.normalization_method}")
