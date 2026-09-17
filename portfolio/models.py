"""
portfolio/models.py — Strongly Typed Domain Models for APEX QUANT Portfolio Construction.

Defines:
  - CandidateRejectionReason & InfeasibilityReason Enums
  - PortfolioCandidate, PortfolioPosition, PortfolioTarget
  - PortfolioAllocation, PortfolioRiskMetrics, PortfolioDiagnostics
  - PortfolioBuildResult (Structured Output Container)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence
import pandas as pd


class CandidateRejectionReason(str, Enum):
    """Explicit reasons why a candidate stock was rejected from portfolio selection."""
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    MISSING_PRICE = "MISSING_PRICE"
    INVALID_PREDICTION = "INVALID_PREDICTION"
    INVALID_VOLATILITY = "INVALID_VOLATILITY"
    INSUFFICIENT_LIQUIDITY = "INSUFFICIENT_LIQUIDITY"
    INVALID_SECTOR = "INVALID_SECTOR"
    BELOW_MIN_SCORE = "BELOW_MIN_SCORE"
    POSITION_LIMIT = "POSITION_LIMIT"
    RISK_LIMIT = "RISK_LIMIT"
    OTHER = "OTHER"


class InfeasibilityReason(str, Enum):
    """Explicit reasons why an allocation algorithm could not satisfy configured constraints."""
    INSUFFICIENT_ELIGIBLE_STOCKS = "INSUFFICIENT_ELIGIBLE_STOCKS"
    CAPITAL_TOO_SMALL = "CAPITAL_TOO_SMALL"
    SECTOR_CONSTRAINT_INFEASIBLE = "SECTOR_CONSTRAINT_INFEASIBLE"
    TURNOVER_CONSTRAINT_INFEASIBLE = "TURNOVER_CONSTRAINT_INFEASIBLE"
    LIQUIDITY_CONSTRAINT_INFEASIBLE = "LIQUIDITY_CONSTRAINT_INFEASIBLE"
    VOLATILITY_TARGET_INFEASIBLE = "VOLATILITY_TARGET_INFEASIBLE"
    CONVERGENCE_FAILURE = "CONVERGENCE_FAILURE"
    OTHER = "OTHER"


@dataclass
class PortfolioCandidate:
    """Instrument evaluated for potential inclusion in the portfolio."""
    symbol: str
    timestamp: pd.Timestamp
    sector: Optional[str]
    rank: Optional[int]
    predicted_return: Optional[float]
    opportunity_score: Optional[float]
    volatility: Optional[float]
    liquidity: Optional[float]  # e.g., 20d median turnover
    current_price: Optional[float]
    is_eligible: bool = True
    rejection_reason: Optional[CandidateRejectionReason] = None


@dataclass
class PortfolioPosition:
    """Current or held portfolio position."""
    symbol: str
    shares: int
    price: float
    value: float
    weight: float


@dataclass
class PortfolioTarget:
    """Target position specification produced by portfolio construction."""
    symbol: str
    target_weight: float
    target_shares: int
    target_value: float
    current_price: float
    sector: Optional[str] = None
    expected_return: Optional[float] = None
    risk_contribution: Optional[float] = None
    delta_shares: int = 0
    delta_value: float = 0.0


@dataclass
class PortfolioAllocation:
    """Result of an allocation algorithm prior to share discretization."""
    target_weights: Dict[str, float]
    cash_weight: float
    method: str
    status: str = "FEASIBLE"  # 'FEASIBLE', 'FALLBACK', 'INFEASIBLE'
    infeasibility_reason: Optional[InfeasibilityReason] = None
    fallback_reason: Optional[str] = None


@dataclass
class PortfolioRiskMetrics:
    """Point-in-time portfolio risk and return metrics."""
    expected_return: float
    portfolio_volatility: float
    return_to_risk_ratio: float
    marginal_risk_contributions: Dict[str, float] = field(default_factory=dict)
    percentage_risk_contributions: Dict[str, float] = field(default_factory=dict)
    sector_risk_contributions: Dict[str, float] = field(default_factory=dict)
    is_covariance_fallback: bool = False


@dataclass
class PortfolioDiagnostics:
    """Diagnostic characteristics of the constructed portfolio."""
    position_count: int
    cash_weight: float
    gross_exposure: float
    turnover: float
    estimated_transaction_cost: float
    hhi_concentration: float
    max_position_weight: float
    largest_position: Optional[str] = None
    largest_sector: Optional[str] = None
    sector_weights: Dict[str, float] = field(default_factory=dict)
    liquidity_utilization: Dict[str, float] = field(default_factory=dict)
    residual_cash: float = 0.0


@dataclass
class PortfolioBuildResult:
    """Comprehensive, strongly typed result emitted by PortfolioBuilder."""
    timestamp: pd.Timestamp
    total_capital: float
    cash: float
    cash_weight: float
    gross_exposure: float
    allocated_value: float
    requested_method: str
    allocation_method: str
    fallback_reason: Optional[str]
    candidate_count: int
    selected_count: int
    positions: Dict[str, PortfolioTarget] = field(default_factory=dict)
    risk_metrics: Optional[PortfolioRiskMetrics] = None
    diagnostics: Optional[PortfolioDiagnostics] = None
    rejected_candidates: List[PortfolioCandidate] = field(default_factory=list)

    def to_dataframe(self) -> pd.DataFrame:
        """Convert target portfolio allocations into a structured DataFrame."""
        rows = []
        for sym, pos in sorted(self.positions.items()):
            rows.append({
                "timestamp": self.timestamp,
                "symbol": sym,
                "sector": pos.sector,
                "target_shares": pos.target_shares,
                "current_price": pos.current_price,
                "target_value": pos.target_value,
                "target_weight": pos.target_weight,
                "delta_shares": pos.delta_shares,
                "delta_value": pos.delta_value,
                "expected_return": pos.expected_return,
                "risk_contribution": pos.risk_contribution,
            })
        return pd.DataFrame(rows)
