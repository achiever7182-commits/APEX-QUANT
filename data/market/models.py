"""
data/market/models.py — Asset-Agnostic Market Data Models for APEX QUANT.

Defines standardized OHLCV bar representations, metadata containers, and converters
supporting Indian equities (NSE/BSE) and global assets with canonical symbols.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import pandas as pd

from core.interfaces.instrument import AssetClass, Exchange, Instrument
from core.interfaces.market_data import Bar


@dataclass(frozen=True)
class MarketBar:
    """
    Standard asset-agnostic OHLCV candlestick representation.
    
    Attributes:
        symbol: Canonical ticker symbol (e.g. 'RELIANCE', 'TCS', 'BTC/USDT')
        exchange: Exchange identifier (e.g. 'NSE', 'BSE', 'BINANCE')
        timestamp: Bar closing or opening timestamp (datetime, timezone-aware or UTC)
        open: Opening price
        high: Highest price during bar period
        low: Lowest price during bar period
        close: Closing price
        volume: Traded volume (number of shares or crypto units)
        adjusted_close: Split and dividend-adjusted closing price (optional)
        adjusted_open: Split and dividend-adjusted opening price (optional)
        adjusted_high: Split and dividend-adjusted high price (optional)
        adjusted_low: Split and dividend-adjusted low price (optional)
        adjusted_volume: Split-adjusted volume (optional)
        vwap: Volume-Weighted Average Price (optional)
        trade_count: Total number of trades in bar (optional)
        turnover: Total traded turnover value in quote currency (optional)
    """
    symbol: str
    exchange: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    adjusted_close: Optional[float] = None
    adjusted_open: Optional[float] = None
    adjusted_high: Optional[float] = None
    adjusted_low: Optional[float] = None
    adjusted_volume: Optional[float] = None
    vwap: Optional[float] = None
    trade_count: Optional[int] = None
    turnover: Optional[float] = None

    def __post_init__(self) -> None:
        # Validate canonical symbol formatting
        clean_symbol = self.symbol.upper().replace(".NS", "").replace(".BO", "").strip()
        if not clean_symbol:
            raise ValueError("Symbol cannot be empty.")
        object.__setattr__(self, "symbol", clean_symbol)

        # Enforce basic numeric sanity checks
        if self.high < self.low:
            raise ValueError(f"High price ({self.high}) cannot be less than low price ({self.low}) for {self.symbol}.")
        if self.volume < 0:
            raise ValueError(f"Volume ({self.volume}) cannot be negative for {self.symbol}.")
        if self.open < 0 or self.high < 0 or self.low < 0 or self.close < 0:
            raise ValueError(f"Prices cannot be negative for {self.symbol}.")

    @property
    def is_bullish(self) -> bool:
        """True if close >= open."""
        return self.close >= self.open

    def to_bar_interface(self) -> Bar:
        """Convert to legacy/generic core.interfaces.market_data.Bar."""
        ts_ms = int(self.timestamp.timestamp() * 1000)
        return Bar(
            symbol=self.symbol,
            timestamp=ts_ms,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
            turnover=self.turnover or (self.close * self.volume),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to flat dictionary for tabular serialization."""
        return {
            "symbol": self.symbol,
            "exchange": self.exchange,
            "timestamp": self.timestamp,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "adjusted_close": self.adjusted_close if self.adjusted_close is not None else self.close,
            "adjusted_open": self.adjusted_open if self.adjusted_open is not None else self.open,
            "adjusted_high": self.adjusted_high if self.adjusted_high is not None else self.high,
            "adjusted_low": self.adjusted_low if self.adjusted_low is not None else self.low,
            "adjusted_volume": self.adjusted_volume if self.adjusted_volume is not None else self.volume,
            "vwap": self.vwap,
            "trade_count": self.trade_count,
            "turnover": self.turnover,
        }

    @classmethod
    def from_series(cls, series: pd.Series, symbol: str, exchange: str = "NSE") -> MarketBar:
        """Factory method to construct MarketBar from a pandas Series."""
        ts = series.get("timestamp") or series.get("Date") or series.name
        if not isinstance(ts, datetime):
            ts = pd.to_datetime(ts).to_pydatetime()
        
        return cls(
            symbol=symbol,
            exchange=exchange,
            timestamp=ts,
            open=float(series["open"]),
            high=float(series["high"]),
            low=float(series["low"]),
            close=float(series["close"]),
            volume=float(series["volume"]),
            adjusted_close=float(series["adjusted_close"]) if "adjusted_close" in series and pd.notna(series["adjusted_close"]) else None,
            adjusted_open=float(series["adjusted_open"]) if "adjusted_open" in series and pd.notna(series["adjusted_open"]) else None,
            adjusted_high=float(series["adjusted_high"]) if "adjusted_high" in series and pd.notna(series["adjusted_high"]) else None,
            adjusted_low=float(series["adjusted_low"]) if "adjusted_low" in series and pd.notna(series["adjusted_low"]) else None,
            adjusted_volume=float(series["adjusted_volume"]) if "adjusted_volume" in series and pd.notna(series["adjusted_volume"]) else None,
            vwap=float(series["vwap"]) if "vwap" in series and pd.notna(series["vwap"]) else None,
            turnover=float(series["turnover"]) if "turnover" in series and pd.notna(series["turnover"]) else None,
        )


@dataclass(frozen=True)
class SymbolMetadata:
    """Canonical metadata for Indian equities and traded assets."""
    symbol: str
    name: str
    exchange: str = "NSE"
    asset_class: str = "EQUITY"
    currency: str = "INR"
    lot_size: int = 1
    tick_size: float = 0.05
    isin: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    is_active: bool = True

    def to_instrument(self) -> Instrument:
        """Convert to core.interfaces.instrument.Instrument."""
        return Instrument(
            symbol=self.symbol,
            asset_class=AssetClass.EQUITY if self.asset_class == "EQUITY" else AssetClass.CRYPTO,
            exchange=Exchange.NSE if self.exchange == "NSE" else Exchange.BINANCE,
            currency=self.currency,
            lot_size=float(self.lot_size),
            tick_size=self.tick_size,
            isin=self.isin,
            is_tradable=self.is_active,
        )
