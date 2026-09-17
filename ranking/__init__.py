"""
ranking — APEX QUANT Cross-Sectional Stock Ranking & Opportunity Engine.

Provides:
  - Multi-factor cross-sectional opportunity scoring and ranking
  - Point-in-time universe compliance and strict eligibility filtering
  - Transparent deterministic tie-breaking (Opportunity Score -> Predicted Return -> Symbol)
  - Diagnostic evaluations (Information Coefficient, return spreads, sector breakdown)
  - Return correlation matrix computation for downstream portfolio construction
  - Benchmark reference rankers (raw prediction, momentum, random)
"""

from ranking.config import DEFAULT_RANKING_WEIGHTS, RankingConfig
from ranking.models import (
    OpportunityRank,
    RankedUniverse,
    RejectionReason,
    ScoringComponents,
)
from ranking.filters import EligibilityFilter
from ranking.scoring import OpportunityScorer
from ranking.ranker import CrossSectionalRanker
from ranking.diagnostics import (
    RankingDiagnosticReport,
    RankingDiagnostics,
    SectorDiagnosticSummary,
)
from ranking.baselines import BaselineRankers

__all__ = [
    "DEFAULT_RANKING_WEIGHTS",
    "RankingConfig",
    "OpportunityRank",
    "RankedUniverse",
    "RejectionReason",
    "ScoringComponents",
    "EligibilityFilter",
    "OpportunityScorer",
    "CrossSectionalRanker",
    "RankingDiagnostics",
    "RankingDiagnosticReport",
    "SectorDiagnosticSummary",
    "BaselineRankers",
]
