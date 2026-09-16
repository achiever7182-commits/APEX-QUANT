"""
core/interfaces/instrument.py — Generic Asset & Instrument Representation for APEX QUANT.

Decouples the system from single-crypto assumptions (e.g. BTC/USDT) so that any
financial instrument (Indian Equities, Indices, ETFs, Commodities, Crypto) can be
modeled cleanly with tick sizes, lot sizes, trading hours, and currencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class AssetClass(str, Enum):
    CRYPTO = "CRYPTO"
    EQUITY = "EQUITY"
    INDEX = "INDEX"
    ETF = "ETF"
    FUTURES = "FUTURES"
    OPTIONS = "OPTIONS"
    COMMODITY = "COMMODITY"
    FOREX = "FOREX"


class Exchange(str, Enum):
    BINANCE = "BINANCE"
    NSE = "NSE"          # National Stock Exchange of India
    BSE = "BSE"          # Bombay Stock Exchange
    MCX = "MCX"          # Multi Commodity Exchange of India
    PAPER = "PAPER"      # Simulated / Sandbox exchange


@dataclass(frozen=True)
class Instrument:
    """
    Asset-agnostic instrument specification.
    
    Attributes:
        symbol: Ticker symbol (e.g., "RELIANCE", "TCS", "BTC/USDT", "NIFTY50")
        asset_class: AssetClass enum (EQUITY, CRYPTO, etc.)
        exchange: Exchange enum (NSE, BINANCE, etc.)
        currency: Base quote currency (e.g., "INR", "USDT")
        lot_size: Minimum tradeable quantity (e.g., 1 for cash equities, 0.00001 for BTC)
        tick_size: Minimum price movement step (e.g., 0.05 for NSE, 0.01 for Binance)
        isin: International Securities Identification Number (for Indian equities)
        is_tradable: Whether the instrument is currently tradeable
    """
    symbol: str
    asset_class: AssetClass = AssetClass.EQUITY
    exchange: Exchange = Exchange.NSE
    currency: str = "INR"
    lot_size: float = 1.0
    tick_size: float = 0.05
    isin: Optional[str] = None
    is_tradable: bool = True

    @classmethod
    def nse_stock(cls, symbol: str, isin: Optional[str] = None) -> Instrument:
        """Helper factory for Indian NSE Cash Equities (e.g. NIFTY 500 stocks)."""
        clean_sym = symbol.upper().replace(".NS", "").strip()
        return cls(
            symbol=clean_sym,
            asset_class=AssetClass.EQUITY,
            exchange=Exchange.NSE,
            currency="INR",
            lot_size=1.0,
            tick_size=0.05,
            isin=isin,
            is_tradable=True,
        )

    @classmethod
    def crypto_pair(cls, symbol: str = "BTC/USDT", exchange: Exchange = Exchange.BINANCE) -> Instrument:
        """Helper factory for Crypto pairs (backward-compatible with existing bot)."""
        return cls(
            symbol=symbol,
            asset_class=AssetClass.CRYPTO,
            exchange=exchange,
            currency="USDT",
            lot_size=0.00001,
            tick_size=0.01,
            isin=None,
            is_tradable=True,
        )
