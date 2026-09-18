"""
execution/models.py — Strongly Typed Domain Models for APEX QUANT Paper Trading Subsystem.

Defines:
  - Enums: OrderSide, OrderType, OrderStatus, RejectionReason, ReconciliationStatus
  - Dataclasses: PaperOrder, PaperFill, PaperPosition, PaperAccount, PaperAuditEvent
  - Reconciliation Models: ReconciliationDiscrepancy, ReconciliationReport
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import pandas as pd


class OrderSide(str, Enum):
    """Trading side of an order."""
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    """Execution type of an order."""
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class OrderStatus(str, Enum):
    """Lifecycle states of a paper trading order."""
    CREATED = "CREATED"
    VALIDATED = "VALIDATED"
    SUBMITTED = "SUBMITTED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"


class RejectionReason(str, Enum):
    """Explicit reasons why an order was rejected by risk or broker."""
    INSUFFICIENT_CASH = "INSUFFICIENT_CASH"
    INSUFFICIENT_SHARES = "INSUFFICIENT_SHARES"
    POSITION_LIMIT = "POSITION_LIMIT"
    SECTOR_LIMIT = "SECTOR_LIMIT"
    TOTAL_EXPOSURE_LIMIT = "TOTAL_EXPOSURE_LIMIT"
    LIQUIDITY_LIMIT = "LIQUIDITY_LIMIT"
    STALE_DATA = "STALE_DATA"
    MARKET_CLOSED = "MARKET_CLOSED"
    DAILY_LOSS_LIMIT = "DAILY_LOSS_LIMIT"
    DRAWDOWN_LIMIT = "DRAWDOWN_LIMIT"
    KILL_SWITCH = "KILL_SWITCH"
    DUPLICATE_ORDER = "DUPLICATE_ORDER"
    INVALID_ORDER = "INVALID_ORDER"
    BROKER_ERROR = "BROKER_ERROR"


class ReconciliationStatus(str, Enum):
    """Overall status of a portfolio reconciliation audit."""
    MATCH = "MATCH"
    MISMATCH = "MISMATCH"
    ERROR = "ERROR"


@dataclass
class PaperOrder:
    """Represents an order within the paper trading lifecycle."""
    symbol: str
    side: OrderSide
    order_type: OrderType
    requested_quantity: int
    order_id: str = field(default_factory=lambda: f"ORD-{uuid.uuid4().hex[:12].upper()}")
    client_order_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    limit_price: Optional[float] = None
    filled_quantity: int = 0
    unfilled_quantity: int = 0
    average_fill_price: float = 0.0
    status: OrderStatus = OrderStatus.CREATED
    rejection_reason: Optional[RejectionReason] = None
    rejection_details: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    validated_at: Optional[str] = None
    submitted_at: Optional[str] = None
    completed_at: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.unfilled_quantity == 0 and self.filled_quantity == 0:
            self.unfilled_quantity = self.requested_quantity

    def to_dict(self) -> Dict[str, Any]:
        return {
            "order_id": self.order_id,
            "client_order_id": self.client_order_id,
            "idempotency_key": self.idempotency_key,
            "symbol": self.symbol,
            "side": self.side.value if isinstance(self.side, OrderSide) else str(self.side),
            "order_type": self.order_type.value if isinstance(self.order_type, OrderType) else str(self.order_type),
            "requested_quantity": self.requested_quantity,
            "filled_quantity": self.filled_quantity,
            "unfilled_quantity": self.unfilled_quantity,
            "limit_price": self.limit_price,
            "average_fill_price": self.average_fill_price,
            "status": self.status.value if isinstance(self.status, OrderStatus) else str(self.status),
            "rejection_reason": self.rejection_reason.value if isinstance(self.rejection_reason, RejectionReason) else (str(self.rejection_reason) if self.rejection_reason else None),
            "rejection_details": self.rejection_details,
            "created_at": self.created_at,
            "validated_at": self.validated_at,
            "submitted_at": self.submitted_at,
            "completed_at": self.completed_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PaperOrder:
        return cls(
            order_id=data["order_id"],
            client_order_id=data.get("client_order_id"),
            idempotency_key=data.get("idempotency_key"),
            symbol=data["symbol"],
            side=OrderSide(data["side"]),
            order_type=OrderType(data["order_type"]),
            requested_quantity=int(data["requested_quantity"]),
            limit_price=float(data["limit_price"]) if data.get("limit_price") is not None else None,
            filled_quantity=int(data.get("filled_quantity", 0)),
            unfilled_quantity=int(data.get("unfilled_quantity", 0)),
            average_fill_price=float(data.get("average_fill_price", 0.0)),
            status=OrderStatus(data.get("status", OrderStatus.CREATED.value)),
            rejection_reason=RejectionReason(data["rejection_reason"]) if data.get("rejection_reason") else None,
            rejection_details=data.get("rejection_details"),
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
            validated_at=data.get("validated_at"),
            submitted_at=data.get("submitted_at"),
            completed_at=data.get("completed_at"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class PaperFill:
    """Represents an execution fill generated for a paper order."""
    fill_id: str
    order_id: str
    symbol: str
    side: OrderSide
    quantity: int
    price: float
    slippage: float
    transaction_cost: float
    total_notional: float
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fill_id": self.fill_id,
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side.value if isinstance(self.side, OrderSide) else str(self.side),
            "quantity": self.quantity,
            "price": self.price,
            "slippage": self.slippage,
            "transaction_cost": self.transaction_cost,
            "total_notional": self.total_notional,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PaperFill:
        return cls(
            fill_id=data["fill_id"],
            order_id=data["order_id"],
            symbol=data["symbol"],
            side=OrderSide(data["side"]),
            quantity=int(data["quantity"]),
            price=float(data["price"]),
            slippage=float(data["slippage"]),
            transaction_cost=float(data["transaction_cost"]),
            total_notional=float(data["total_notional"]),
            timestamp=data.get("timestamp", datetime.now(timezone.utc).isoformat()),
        )


@dataclass
class PaperPosition:
    """Represents a current holding position in the paper portfolio."""
    symbol: str
    shares: int
    average_cost: float
    current_price: float
    market_value: float = 0.0
    cost_basis: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    last_updated: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self):
        self.recompute(self.current_price)

    def recompute(self, mark_price: float) -> None:
        self.current_price = mark_price
        self.market_value = self.shares * mark_price
        self.cost_basis = self.shares * self.average_cost
        self.unrealized_pnl = self.market_value - self.cost_basis

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "shares": self.shares,
            "average_cost": self.average_cost,
            "current_price": self.current_price,
            "market_value": self.market_value,
            "cost_basis": self.cost_basis,
            "unrealized_pnl": self.unrealized_pnl,
            "realized_pnl": self.realized_pnl,
            "last_updated": self.last_updated,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PaperPosition:
        pos = cls(
            symbol=data["symbol"],
            shares=int(data["shares"]),
            average_cost=float(data["average_cost"]),
            current_price=float(data["current_price"]),
            market_value=float(data.get("market_value", 0.0)),
            cost_basis=float(data.get("cost_basis", 0.0)),
            unrealized_pnl=float(data.get("unrealized_pnl", 0.0)),
            realized_pnl=float(data.get("realized_pnl", 0.0)),
            last_updated=data.get("last_updated", datetime.now(timezone.utc).isoformat()),
        )
        return pos


@dataclass
class PaperAccount:
    """Represents the complete account balance and telemetry state."""
    initial_capital: float = 1_000_000.0
    cash: float = 1_000_000.0
    positions_value: float = 0.0
    total_equity: float = 1_000_000.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    total_fees: float = 0.0
    total_slippage: float = 0.0
    total_turnover: float = 0.0
    peak_equity: float = 1_000_000.0
    max_drawdown: float = 0.0
    daily_pnl: float = 0.0
    start_of_day_equity: float = 1_000_000.0
    last_updated: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def update_totals(self, positions_value: float, unrealized_pnl: float) -> None:
        self.positions_value = positions_value
        self.unrealized_pnl = unrealized_pnl
        self.total_equity = self.cash + positions_value
        self.daily_pnl = self.total_equity - self.start_of_day_equity
        if self.total_equity > self.peak_equity:
            self.peak_equity = self.total_equity
        dd = (self.peak_equity - self.total_equity) / self.peak_equity if self.peak_equity > 0 else 0.0
        if dd > self.max_drawdown:
            self.max_drawdown = dd
        self.last_updated = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "initial_capital": self.initial_capital,
            "cash": self.cash,
            "positions_value": self.positions_value,
            "total_equity": self.total_equity,
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": self.unrealized_pnl,
            "total_fees": self.total_fees,
            "total_slippage": self.total_slippage,
            "total_turnover": self.total_turnover,
            "peak_equity": self.peak_equity,
            "max_drawdown": self.max_drawdown,
            "daily_pnl": self.daily_pnl,
            "start_of_day_equity": self.start_of_day_equity,
            "last_updated": self.last_updated,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PaperAccount:
        return cls(
            initial_capital=float(data.get("initial_capital", 1_000_000.0)),
            cash=float(data.get("cash", 1_000_000.0)),
            positions_value=float(data.get("positions_value", 0.0)),
            total_equity=float(data.get("total_equity", 1_000_000.0)),
            realized_pnl=float(data.get("realized_pnl", 0.0)),
            unrealized_pnl=float(data.get("unrealized_pnl", 0.0)),
            total_fees=float(data.get("total_fees", 0.0)),
            total_slippage=float(data.get("total_slippage", 0.0)),
            total_turnover=float(data.get("total_turnover", 0.0)),
            peak_equity=float(data.get("peak_equity", 1_000_000.0)),
            max_drawdown=float(data.get("max_drawdown", 0.0)),
            daily_pnl=float(data.get("daily_pnl", 0.0)),
            start_of_day_equity=float(data.get("start_of_day_equity", 1_000_000.0)),
            last_updated=data.get("last_updated", datetime.now(timezone.utc).isoformat()),
        )


@dataclass
class PaperAuditEvent:
    """Structured audit trail record for paper trading activity."""
    event_type: str
    payload: Dict[str, Any]
    event_id: str = field(default_factory=lambda: f"EVT-{uuid.uuid4().hex[:12].upper()}")
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    level: str = "INFO"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "level": self.level,
            "payload": self.payload,
        }


@dataclass
class ReconciliationDiscrepancy:
    """Specific mismatch item identified during reconciliation."""
    category: str  # e.g. 'SHARES', 'CASH', 'MISSING_FILL', 'DUPLICATE_FILL', 'BALANCE_IDENTITY'
    symbol: Optional[str]
    expected_value: Any
    actual_value: Any
    difference: Optional[float] = None
    details: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category,
            "symbol": self.symbol,
            "expected_value": self.expected_value,
            "actual_value": self.actual_value,
            "difference": self.difference,
            "details": self.details,
        }


@dataclass
class ReconciliationReport:
    """Comprehensive portfolio reconciliation audit result."""
    timestamp: str
    status: ReconciliationStatus
    discrepancies: List[ReconciliationDiscrepancy] = field(default_factory=list)
    expected_equity: float = 0.0
    actual_equity: float = 0.0
    cash_difference: float = 0.0
    is_clean: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "status": self.status.value,
            "is_clean": self.is_clean,
            "expected_equity": self.expected_equity,
            "actual_equity": self.actual_equity,
            "cash_difference": self.cash_difference,
            "discrepancies": [d.to_dict() for d in self.discrepancies],
        }


class BrokerConnectionState(str, Enum):
    """Connection states for external and simulated brokers."""
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    RECONNECTING = "RECONNECTING"
    ERROR = "ERROR"


@dataclass
class BrokerCapabilities:
    """Explicit capability matrix defining what an execution broker supports."""
    supports_market_orders: bool = True
    supports_limit_orders: bool = True
    supports_stop_orders: bool = False
    supports_order_cancellation: bool = True
    supports_order_status_query: bool = True
    supports_positions_query: bool = True
    supports_account_balance_query: bool = True
    supports_fills_query: bool = True
    supports_integer_shares: bool = True
    supports_fractional_shares: bool = False
    supports_shorting: bool = False
    supports_live_orders: bool = False
    broker_name: str = "AbstractBroker"
    supported_exchanges: List[str] = field(default_factory=lambda: ["NSE"])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "broker_name": self.broker_name,
            "supports_market_orders": self.supports_market_orders,
            "supports_limit_orders": self.supports_limit_orders,
            "supports_stop_orders": self.supports_stop_orders,
            "supports_order_cancellation": self.supports_order_cancellation,
            "supports_order_status_query": self.supports_order_status_query,
            "supports_positions_query": self.supports_positions_query,
            "supports_account_balance_query": self.supports_account_balance_query,
            "supports_fills_query": self.supports_fills_query,
            "supports_integer_shares": self.supports_integer_shares,
            "supports_fractional_shares": self.supports_fractional_shares,
            "supports_shorting": self.supports_shorting,
            "supports_live_orders": self.supports_live_orders,
            "supported_exchanges": self.supported_exchanges,
        }

