"""
core/interfaces/broker.py — Generic Broker & Execution Abstraction for APEX QUANT.

Decouples the system from direct exchange API calls (CCXT/Binance), enabling:
- PaperBroker (local simulation with realistic fees/taxes)
- BinanceTestnetAdapter (Crypto testnet)
- Indian Equity Brokers (Zerodha Kite Connect, Upstox, Angel One, Shoonya, Dhan)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional
from datetime import datetime

from core.interfaces.instrument import Instrument


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_LOSS = "STOP_LOSS"
    STOP_LIMIT = "STOP_LIMIT"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class ProductType(str, Enum):
    DELIVERY = "DELIVERY"  # Cash equity delivery (CNC in Indian markets)
    INTRADAY = "INTRADAY"  # Intraday margin (MIS in Indian markets)
    SPOT = "SPOT"          # Standard spot trading (Crypto)


@dataclass
class Order:
    """Standardized trade order instruction."""
    instrument: Instrument
    side: OrderSide
    quantity: float
    order_type: OrderType = OrderType.MARKET
    price: Optional[float] = None
    stop_price: Optional[float] = None
    product_type: ProductType = ProductType.DELIVERY
    client_order_id: str = ""
    broker_order_id: Optional[str] = None
    status: OrderStatus = OrderStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)
    filled_quantity: float = 0.0
    average_fill_price: float = 0.0
    fee_paid: float = 0.0


@dataclass
class OrderFill:
    """Execution fill confirmation."""
    order_id: str
    instrument: Instrument
    side: OrderSide
    fill_price: float
    filled_quantity: float
    fee_paid: float
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Position:
    """Represents a current holding for a specific instrument."""
    instrument: Instrument
    quantity: float
    entry_price: float
    current_price: float
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    entry_time: Optional[datetime] = None

    @property
    def market_value(self) -> float:
        return self.quantity * self.current_price

    @property
    def cost_basis(self) -> float:
        return self.quantity * self.entry_price

    @property
    def return_pct(self) -> float:
        return (self.current_price - self.entry_price) / self.entry_price if self.entry_price > 0 else 0.0


@dataclass
class PortfolioSnapshot:
    """Point-in-time snapshot of the overall portfolio state."""
    cash: float
    equity: float
    positions: Dict[str, Position] = field(default_factory=dict)
    daily_pnl: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)

    @property
    def open_position_count(self) -> int:
        return len([p for p in self.positions.values() if p.quantity > 0])


class IBroker(ABC):
    """
    Abstract Broker interface.
    
    Subclasses must implement:
    - PaperBroker (simulated execution)
    - BinanceBrokerAdapter (mapping existing Binance client)
    - IndianBrokerAdapter (mapping compliant Indian broker APIs)
    """

    @abstractmethod
    def get_cash_balance(self, currency: str = "INR") -> float:
        """Fetch free tradeable cash in the given currency."""
        raise NotImplementedError

    @abstractmethod
    def get_positions(self) -> List[Position]:
        """Fetch all currently open positions."""
        raise NotImplementedError

    @abstractmethod
    def place_order(self, order: Order) -> OrderFill:
        """Place a buy or sell order and return the execution fill."""
        raise NotImplementedError

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open pending/limit order."""
        raise NotImplementedError

    @abstractmethod
    def get_order_status(self, order_id: str) -> OrderStatus:
        """Query current execution status of an order."""
        raise NotImplementedError

    @abstractmethod
    def reconcile(self) -> PortfolioSnapshot:
        """Reconcile local holdings against the broker's actual source of truth."""
        raise NotImplementedError
