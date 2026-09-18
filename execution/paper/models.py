"""
execution/paper/models.py — Domain Models & State Machine for Paper Trading Orchestration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from execution.models import (
    OrderStatus,
    PaperAccount,
    PaperFill,
    PaperOrder,
    ReconciliationReport,
)
from execution.paper.session_models import (
    InvalidSessionTransitionError,
    MultiSessionConfig,
    PaperPerformanceReport,
    SessionRecord,
    SessionState,
    SessionTransitionValidator,
)


class CycleState(str, Enum):
    """Explicit lifecycle states of an end-to-end paper trading cycle."""
    CREATED = "CREATED"
    MARKET_VALIDATED = "MARKET_VALIDATED"
    DATA_READY = "DATA_READY"
    FEATURES_READY = "FEATURES_READY"
    PREDICTIONS_READY = "PREDICTIONS_READY"
    RANKING_READY = "RANKING_READY"
    PORTFOLIO_READY = "PORTFOLIO_READY"
    RISK_CHECKED = "RISK_CHECKED"
    ORDERS_SUBMITTED = "ORDERS_SUBMITTED"
    FILLED = "FILLED"
    RECONCILED = "RECONCILED"
    COMPLETED = "COMPLETED"

    # Terminal / Failure states
    MARKET_CLOSED_SKIPPED = "MARKET_CLOSED_SKIPPED"
    DATA_FAILED = "DATA_FAILED"
    MODEL_FAILED = "MODEL_FAILED"
    PORTFOLIO_FAILED = "PORTFOLIO_FAILED"
    RISK_BLOCKED = "RISK_BLOCKED"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    RECONCILIATION_FAILED = "RECONCILIATION_FAILED"
    ALREADY_PROCESSED = "ALREADY_PROCESSED"


@dataclass
class SignalSnapshot:
    """Point-in-time quantitative prediction snapshot for a single stock."""
    symbol: str
    timestamp: str
    predicted_return: float
    model_id: str
    confidence: float = 1.0
    features: Dict[str, float] = field(default_factory=dict)
    data_timestamp: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "predicted_return": round(self.predicted_return, 6),
            "model_id": self.model_id,
            "confidence": round(self.confidence, 4),
            "features_count": len(self.features),
            "data_timestamp": self.data_timestamp,
        }


@dataclass
class PortfolioDecision:
    """Target portfolio position decision for a single stock."""
    symbol: str
    current_shares: int
    target_shares: int
    delta_shares: int
    target_weight: float
    estimated_price: float
    estimated_notional: float
    reason: str = "REBALANCE"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "current_shares": self.current_shares,
            "target_shares": self.target_shares,
            "delta_shares": self.delta_shares,
            "target_weight": round(self.target_weight, 4),
            "estimated_price": round(self.estimated_price, 2),
            "estimated_notional": round(self.estimated_notional, 2),
            "reason": self.reason,
        }


@dataclass
class CycleResult:
    """Comprehensive result of an end-to-end paper trading execution cycle."""
    cycle_id: str
    state: CycleState
    timestamp: str
    market_session: str
    eligible_stocks: List[str] = field(default_factory=list)
    excluded_stocks: Dict[str, str] = field(default_factory=dict)
    signals: List[SignalSnapshot] = field(default_factory=list)
    decisions: List[PortfolioDecision] = field(default_factory=list)
    orders_generated: List[PaperOrder] = field(default_factory=list)
    orders_rejected: List[PaperOrder] = field(default_factory=list)
    fills: List[PaperFill] = field(default_factory=list)
    account_snapshot: Optional[Dict[str, Any]] = None
    reconciliation_report: Optional[Dict[str, Any]] = None
    duration_ms: float = 0.0
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "state": self.state.value if isinstance(self.state, CycleState) else str(self.state),
            "timestamp": self.timestamp,
            "market_session": self.market_session,
            "eligible_stocks_count": len(self.eligible_stocks),
            "eligible_stocks": self.eligible_stocks,
            "excluded_stocks": self.excluded_stocks,
            "signals_count": len(self.signals),
            "signals": [s.to_dict() for s in self.signals],
            "decisions_count": len(self.decisions),
            "decisions": [d.to_dict() for d in self.decisions],
            "orders_generated_count": len(self.orders_generated),
            "orders_rejected_count": len(self.orders_rejected),
            "fills_count": len(self.fills),
            "account_snapshot": self.account_snapshot,
            "reconciliation": self.reconciliation_report,
            "duration_ms": round(self.duration_ms, 2),
            "error_message": self.error_message,
        }
