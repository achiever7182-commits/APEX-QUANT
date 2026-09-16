"""
core/interfaces/market_data.py — Generic Market Data & Feed Interfaces for APEX QUANT.

Establishes the standard contract for historical and real-time market data providers,
allowing clean swapping between crypto feeds (Binance) and Indian equity feeds (NSE/BSE).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Optional, Sequence
from datetime import datetime

from core.interfaces.instrument import Instrument


@dataclass(frozen=True)
class Bar:
    """
    Standardized OHLCV candlestick bar.
    
    Compatible with existing core.strategy.MarketData while adding support
    for Indian stock market fields like turnover and open interest.
    """
    symbol: str
    timestamp: int            # Epoch milliseconds
    open: float
    high: float
    low: float
    close: float
    volume: float
    turnover: float = 0.0     # Value traded in quote currency (INR/USDT)
    open_interest: float = 0.0 # Open interest for F&O contracts

    @property
    def datetime_utc(self) -> datetime:
        return datetime.utcfromtimestamp(self.timestamp / 1000.0)

    @property
    def is_bullish(self) -> bool:
        return self.close >= self.open


@dataclass(frozen=True)
class Tick:
    """A real-time price trade tick."""
    symbol: str
    price: float
    quantity: float
    timestamp: int            # Epoch milliseconds
    side: Optional[str] = None # "BUY", "SELL", or None if unknown


class IMarketDataFeed(ABC):
    """
    Abstract interface for any market data provider.
    
    Subclasses will implement this for:
    - BinanceTestnetAdapter (Crypto)
    - Indian Equity providers (e.g. yfinance, Kite, Shoonya, TrueData, Dhan)
    - Synthetic / CSV replay feeds (Backtesting)
    """

    @abstractmethod
    def fetch_historical_bars(
        self,
        instrument: Instrument,
        timeframe: str = "1d",
        limit: int = 100,
        since_days_ago: Optional[int] = None,
    ) -> list[Bar]:
        """Fetch historical completed bars for an instrument."""
        raise NotImplementedError

    @abstractmethod
    def fetch_latest_price(self, instrument: Instrument) -> float:
        """Fetch the most recent traded price for an instrument."""
        raise NotImplementedError

    @abstractmethod
    def subscribe_ticks(
        self,
        instruments: Sequence[Instrument],
        on_tick: Callable[[Tick], None],
    ) -> None:
        """Subscribe to real-time tick streaming for one or more instruments."""
        raise NotImplementedError

    @abstractmethod
    def stop(self) -> None:
        """Halt any active background streaming threads or sockets."""
        raise NotImplementedError
