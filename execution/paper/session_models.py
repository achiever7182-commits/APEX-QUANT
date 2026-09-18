"""
execution/paper/session_models.py — Domain Models & State Machine for Multi-Session Paper Simulation.

Defines:
  - SessionState: Explicit lifecycle states for simulated trading sessions.
  - SessionTransitionValidator: Strict state transition rules preventing illegal state mutation.
  - MultiSessionConfig: Configuration parameters for multi-session simulation.
  - SessionRecord: Persistent point-in-time audit record for a simulated trading day/session.
  - PaperPerformanceReport: Standardized simulated paper performance metrics clearly labeled
    as non-live research results.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set


class SessionState(str, Enum):
    """Explicit lifecycle states of a paper trading market session."""
    INITIALIZING = "INITIALIZING"
    PRE_MARKET = "PRE_MARKET"
    READY = "READY"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    RECONCILING = "RECONCILING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ABORTED = "ABORTED"


class InvalidSessionTransitionError(ValueError):
    """Raised when an illegal state transition is attempted in the session lifecycle."""
    pass


class SessionTransitionValidator:
    """Enforces explicit state transitions for the session state machine."""

    _ALLOWED_TRANSITIONS: Dict[SessionState, Set[SessionState]] = {
        SessionState.INITIALIZING: {SessionState.PRE_MARKET, SessionState.FAILED, SessionState.ABORTED},
        SessionState.PRE_MARKET: {SessionState.READY, SessionState.FAILED, SessionState.ABORTED},
        SessionState.READY: {SessionState.RUNNING, SessionState.FAILED, SessionState.ABORTED},
        SessionState.RUNNING: {SessionState.PAUSED, SessionState.RECONCILING, SessionState.FAILED, SessionState.ABORTED},
        SessionState.PAUSED: {SessionState.RUNNING, SessionState.FAILED, SessionState.ABORTED},
        SessionState.RECONCILING: {SessionState.COMPLETED, SessionState.FAILED, SessionState.ABORTED},
        SessionState.COMPLETED: set(),  # Terminal
        SessionState.FAILED: set(),     # Terminal
        SessionState.ABORTED: set(),    # Terminal
    }

    @classmethod
    def validate_transition(cls, from_state: SessionState, to_state: SessionState) -> None:
        """
        Validate that the transition from `from_state` to `to_state` is legal.
        Raises InvalidSessionTransitionError if transition is forbidden.
        """
        allowed = cls._ALLOWED_TRANSITIONS.get(from_state, set())
        if to_state not in allowed:
            raise InvalidSessionTransitionError(
                f"Illegal session state transition from {from_state.value} to {to_state.value}. "
                f"Allowed target states: {[s.value for s in allowed] or 'None (Terminal)'}."
            )

    @classmethod
    def is_terminal(cls, state: SessionState) -> bool:
        """Return True if state is terminal (no further transitions allowed)."""
        return state in {SessionState.COMPLETED, SessionState.FAILED, SessionState.ABORTED}


@dataclass
class MultiSessionConfig:
    """Configuration for multi-session paper trading simulation."""
    sessions_count: int = 5
    start_date: str = "2024-04-15"
    end_date: Optional[str] = None
    initial_capital: float = 1_000_000.0
    rebalance_frequency: str = "daily"
    random_seed: Optional[int] = 42
    universe: List[str] = field(default_factory=lambda: ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"])
    slippage_bps: float = 5.0
    transaction_cost_bps: float = 10.0
    allocation_method: str = "constrained"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sessions_count": self.sessions_count,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "initial_capital": self.initial_capital,
            "rebalance_frequency": self.rebalance_frequency,
            "random_seed": self.random_seed,
            "universe": list(self.universe),
            "slippage_bps": self.slippage_bps,
            "transaction_cost_bps": self.transaction_cost_bps,
            "allocation_method": self.allocation_method,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> MultiSessionConfig:
        return cls(
            sessions_count=int(d.get("sessions_count", 5)),
            start_date=str(d.get("start_date", "2024-04-15")),
            end_date=d.get("end_date"),
            initial_capital=float(d.get("initial_capital", 1_000_000.0)),
            rebalance_frequency=str(d.get("rebalance_frequency", "daily")),
            random_seed=d.get("random_seed") if d.get("random_seed") is not None else 42,
            universe=list(d.get("universe", ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"])),
            slippage_bps=float(d.get("slippage_bps", 5.0)),
            transaction_cost_bps=float(d.get("transaction_cost_bps", 10.0)),
            allocation_method=str(d.get("allocation_method", "constrained")),
        )


@dataclass
class SessionRecord:
    """Persistent point-in-time audit record for a single simulated market session."""
    session_id: str
    simulation_date: str
    start_time: str
    end_time: Optional[str] = None
    state: SessionState = SessionState.INITIALIZING
    cycle_count: int = 0
    orders_count: int = 0
    fills_count: int = 0
    fees: float = 0.0
    slippage: float = 0.0
    equity: float = 1_000_000.0
    cash: float = 1_000_000.0
    positions_value: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    drawdown: float = 0.0
    reconciliation_status: str = "PENDING"
    error_count: int = 0
    error_message: Optional[str] = None
    cycles: List[Dict[str, Any]] = field(default_factory=list)
    positions_snapshot: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "simulation_date": self.simulation_date,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "state": self.state.value if isinstance(self.state, SessionState) else str(self.state),
            "cycle_count": self.cycle_count,
            "orders_count": self.orders_count,
            "fills_count": self.fills_count,
            "fees": round(self.fees, 2),
            "slippage": round(self.slippage, 2),
            "equity": round(self.equity, 2),
            "cash": round(self.cash, 2),
            "positions_value": round(self.positions_value, 2),
            "realized_pnl": round(self.realized_pnl, 2),
            "unrealized_pnl": round(self.unrealized_pnl, 2),
            "drawdown": round(self.drawdown, 4),
            "reconciliation_status": self.reconciliation_status,
            "error_count": self.error_count,
            "error_message": self.error_message,
            "cycles": list(self.cycles),
            "positions_snapshot": dict(self.positions_snapshot),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> SessionRecord:
        state_val = d.get("state", "INITIALIZING")
        try:
            st = SessionState(state_val)
        except ValueError:
            st = SessionState.INITIALIZING

        return cls(
            session_id=str(d.get("session_id", "")),
            simulation_date=str(d.get("simulation_date", "")),
            start_time=str(d.get("start_time", "")),
            end_time=d.get("end_time"),
            state=st,
            cycle_count=int(d.get("cycle_count", 0)),
            orders_count=int(d.get("orders_count", 0)),
            fills_count=int(d.get("fills_count", 0)),
            fees=float(d.get("fees", 0.0)),
            slippage=float(d.get("slippage", 0.0)),
            equity=float(d.get("equity", 1_000_000.0)),
            cash=float(d.get("cash", 1_000_000.0)),
            positions_value=float(d.get("positions_value", 0.0)),
            realized_pnl=float(d.get("realized_pnl", 0.0)),
            unrealized_pnl=float(d.get("unrealized_pnl", 0.0)),
            drawdown=float(d.get("drawdown", 0.0)),
            reconciliation_status=str(d.get("reconciliation_status", "PENDING")),
            error_count=int(d.get("error_count", 0)),
            error_message=d.get("error_message"),
            cycles=list(d.get("cycles", [])),
            positions_snapshot=dict(d.get("positions_snapshot", {})),
        )


@dataclass
class PaperPerformanceReport:
    """
    Simulated Paper Performance Metrics Report.
    Clearly labeled as simulated research validation with zero live performance claims.
    """
    disclaimer: str = "SIMULATED PAPER PERFORMANCE — Research & operational validation only. Zero real execution, zero profitability guarantees."
    universe: List[str] = field(default_factory=list)
    date_range: Dict[str, str] = field(default_factory=dict)
    initial_capital: float = 1_000_000.0
    final_equity: float = 1_000_000.0
    total_return_pct: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    total_fees: float = 0.0
    total_slippage: float = 0.0
    total_costs: float = 0.0
    turnover: float = 0.0
    max_drawdown_pct: float = 0.0
    annualized_volatility_pct: float = 0.0
    sharpe_ratio: Optional[float] = None
    sortino_ratio: Optional[float] = None
    win_rate_pct: float = 0.0
    trade_count: int = 0
    sessions_count: int = 0
    simulation_seed: Optional[int] = None
    model_version: str = "ridge_v1"
    data_source: str = "historical_market_bars"
    equity_curve: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "disclaimer": self.disclaimer,
            "universe": list(self.universe),
            "date_range": dict(self.date_range),
            "initial_capital": round(self.initial_capital, 2),
            "final_equity": round(self.final_equity, 2),
            "total_return_pct": round(self.total_return_pct, 4),
            "realized_pnl": round(self.realized_pnl, 2),
            "unrealized_pnl": round(self.unrealized_pnl, 2),
            "total_fees": round(self.total_fees, 2),
            "total_slippage": round(self.total_slippage, 2),
            "total_costs": round(self.total_costs, 2),
            "turnover": round(self.turnover, 4),
            "max_drawdown_pct": round(self.max_drawdown_pct, 4),
            "annualized_volatility_pct": round(self.annualized_volatility_pct, 4),
            "sharpe_ratio": round(self.sharpe_ratio, 4) if self.sharpe_ratio is not None else None,
            "sortino_ratio": round(self.sortino_ratio, 4) if self.sortino_ratio is not None else None,
            "win_rate_pct": round(self.win_rate_pct, 2),
            "trade_count": self.trade_count,
            "sessions_count": self.sessions_count,
            "simulation_seed": self.simulation_seed,
            "model_version": self.model_version,
            "data_source": self.data_source,
            "equity_curve": list(self.equity_curve),
        }
