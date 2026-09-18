"""
data/realtime/models.py — Strongly Typed Domain Models for Real-Time Indian Equity Market Data.

Defines:
  - Enums: ConnectionState, MarketSessionState
  - Dataclasses: NormalizedSymbol, RealtimeQuote, FeedHealthMetrics, AggregatedBar
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import pandas as pd


class ConnectionState(str, Enum):
    """Lifecycle states of the real-time market data connection."""
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    DEGRADED = "DEGRADED"
    RECONNECTING = "RECONNECTING"
    FAILED = "FAILED"


class MarketSessionState(str, Enum):
    """Exchange session states according to NSE market schedule."""
    PRE_MARKET = "PRE_MARKET"
    REGULAR = "REGULAR"
    POST_MARKET = "POST_MARKET"
    CLOSED = "CLOSED"
    WEEKEND = "WEEKEND"
    HOLIDAY = "HOLIDAY"


@dataclass(frozen=True)
class NormalizedSymbol:
    """
    Canonical representation of an Indian equity instrument.
    
    Format: '<EXCHANGE>:<TICKER>' e.g. 'NSE:RELIANCE', 'BSE:TCS'
    """
    ticker: str
    exchange: str = "NSE"

    def __post_init__(self) -> None:
        clean_ticker = self.ticker.upper().strip()
        clean_exchange = self.exchange.upper().strip()

        # Strip suffixes like .NS, .BO if present in ticker string
        clean_ticker = clean_ticker.replace(".NS", "").replace(".BO", "")
        if ":" in clean_ticker:
            parts = clean_ticker.split(":", 1)
            clean_exchange = parts[0]
            clean_ticker = parts[1]

        if not clean_ticker or not clean_ticker.isalnum():
            raise ValueError(f"Invalid ticker: '{self.ticker}'. Must be non-empty alphanumeric.")
        if clean_exchange not in ("NSE", "BSE"):
            raise ValueError(f"Invalid exchange: '{self.exchange}'. Must be 'NSE' or 'BSE'.")

        object.__setattr__(self, "ticker", clean_ticker)
        object.__setattr__(self, "exchange", clean_exchange)

    @property
    def canonical(self) -> str:
        """Return canonical exchange-prefixed string e.g. 'NSE:RELIANCE'."""
        return f"{self.exchange}:{self.ticker}"

    def __str__(self) -> str:
        return self.canonical

    def __repr__(self) -> str:
        return f"NormalizedSymbol('{self.canonical}')"


@dataclass(frozen=True)
class RealtimeQuote:
    """
    Normalized real-time quote for an equity instrument.
    
    Represents latest price, top of book, session statistics, and validation metadata.
    """
    symbol: str  # Canonical symbol string, e.g. 'NSE:RELIANCE'
    exchange: str
    timestamp: datetime
    last_price: float
    volume: float = 0.0
    bid: Optional[float] = None
    ask: Optional[float] = None
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    previous_close: Optional[float] = None
    provider_timestamp: Optional[datetime] = None
    received_timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    sequence_number: Optional[int] = None
    data_source: str = "REALTIME"
    market_session_state: MarketSessionState = MarketSessionState.REGULAR
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "exchange": self.exchange,
            "timestamp": self.timestamp.isoformat() if isinstance(self.timestamp, datetime) else str(self.timestamp),
            "last_price": self.last_price,
            "volume": self.volume,
            "bid": self.bid,
            "ask": self.ask,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "previous_close": self.previous_close,
            "provider_timestamp": self.provider_timestamp.isoformat() if self.provider_timestamp else None,
            "received_timestamp": self.received_timestamp.isoformat() if self.received_timestamp else None,
            "sequence_number": self.sequence_number,
            "data_source": self.data_source,
            "market_session_state": self.market_session_state.value,
            "metadata": self.metadata,
        }


@dataclass
class FeedHealthMetrics:
    """Structured metrics container tracking data feed throughput and quality."""
    connection_state: ConnectionState = ConnectionState.DISCONNECTED
    messages_received: int = 0
    valid_messages: int = 0
    invalid_messages: int = 0
    dropped_messages: int = 0
    duplicate_messages: int = 0
    stale_events: int = 0
    reconnect_count: int = 0
    last_event_timestamp: Optional[str] = None
    last_receive_timestamp: Optional[str] = None
    subscribed_symbols_count: int = 0
    stale_symbols_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "connection_state": self.connection_state.value,
            "messages_received": self.messages_received,
            "valid_messages": self.valid_messages,
            "invalid_messages": self.invalid_messages,
            "dropped_messages": self.dropped_messages,
            "duplicate_messages": self.duplicate_messages,
            "stale_events": self.stale_events,
            "reconnect_count": self.reconnect_count,
            "last_event_timestamp": self.last_event_timestamp,
            "last_receive_timestamp": self.last_receive_timestamp,
            "subscribed_symbols_count": self.subscribed_symbols_count,
            "stale_symbols_count": self.stale_symbols_count,
        }


@dataclass
class AggregatedBar:
    """Discrete candlestick bar formed from streaming real-time quote updates."""
    symbol: str
    start_time: datetime
    end_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    interval_seconds: int = 300
    ticks_count: int = 1
    is_complete: bool = False

    def update(self, price: float, volume_delta: float, tick_time: datetime) -> None:
        """Incorporate new tick into active bar."""
        if price > self.high:
            self.high = price
        if price < self.low:
            self.low = price
        self.close = price
        self.volume += max(0.0, volume_delta)
        self.ticks_count += 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "interval_seconds": self.interval_seconds,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "ticks_count": self.ticks_count,
            "is_complete": self.is_complete,
        }
