"""
ranking/models.py — Domain Models for Stock Ranking and Opportunity Scoring.

Defines:
  - RejectionReason: Structured enumeration of eligibility failure modes
  - ScoringComponents: Breakdown of constituent sub-scores
  - OpportunityRank: Entity representing a ranked opportunity with diagnostics
  - RankedUniverse: Structured collection of ranked assets at a specific timestamp
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
import pandas as pd


class RejectionReason(str, Enum):
    """Explicit deterministic reasons for excluding an equity from ranking."""
    NOT_IN_UNIVERSE = "NOT_IN_UNIVERSE"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    MISSING_PREDICTION = "MISSING_PREDICTION"
    INVALID_PRICE = "INVALID_PRICE"
    LOW_LIQUIDITY = "LOW_LIQUIDITY"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    DELISTED = "DELISTED"
    BELOW_SCORE_THRESHOLD = "BELOW_SCORE_THRESHOLD"


@dataclass(frozen=True)
class ScoringComponents:
    """Breakdown of individual normalized scoring factors."""
    prediction_score: float
    risk_adjusted_score: float
    relative_strength_score: float
    momentum_score: float
    trend_score: float
    regime_score: float
    liquidity_score: float

    def to_dict(self) -> Dict[str, float]:
        return asdict(self)


@dataclass
class OpportunityRank:
    """Individual stock ranking entry at a specific point in time."""
    timestamp: pd.Timestamp
    symbol: str
    rank: Optional[int]
    opportunity_score: Optional[float]
    is_eligible: bool
    predicted_return: Optional[float] = None
    rejection_reason: Optional[RejectionReason] = None
    scoring_components: Optional[ScoringComponents] = None
    sector: Optional[str] = None
    industry: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "timestamp": self.timestamp,
            "symbol": self.symbol,
            "rank": self.rank,
            "opportunity_score": self.opportunity_score,
            "is_eligible": self.is_eligible,
            "predicted_return": self.predicted_return,
            "rejection_reason": self.rejection_reason.value if self.rejection_reason else None,
            "sector": self.sector,
            "industry": self.industry,
        }
        if self.scoring_components:
            d.update({f"score_{k}": v for k, v in self.scoring_components.to_dict().items()})
        return d


@dataclass
class RankedUniverse:
    """Container for the entire ranked cross-section at a single timestamp."""
    timestamp: pd.Timestamp
    ranked_items: List[OpportunityRank]
    total_evaluated: int
    eligible_count: int
    rejected_count: int
    top_k: Optional[int] = None

    @property
    def eligible_opportunities(self) -> List[OpportunityRank]:
        """Return only eligible opportunities sorted by rank ascending."""
        return [item for item in self.ranked_items if item.is_eligible and item.rank is not None]

    @property
    def top_opportunities(self) -> List[OpportunityRank]:
        """Return top K eligible opportunities."""
        el = self.eligible_opportunities
        if self.top_k is not None:
            return el[:self.top_k]
        return el

    def to_dataframe(self) -> pd.DataFrame:
        """Convert all entries (eligible and rejected) into a tabular DataFrame."""
        if not self.ranked_items:
            return pd.DataFrame()
        records = [item.to_dict() for item in self.ranked_items]
        df = pd.DataFrame(records)
        # Order columns cleanly
        col_order = [
            "timestamp", "symbol", "rank", "opportunity_score", "predicted_return",
            "is_eligible", "rejection_reason", "sector",
        ]
        score_cols = [c for c in df.columns if c.startswith("score_")]
        other_cols = [c for c in df.columns if c not in col_order and c not in score_cols]
        return df[col_order + score_cols + other_cols]
