"""
data/realtime/normalizer.py — Symbol & Quote Normalization Engine.

Provides canonical symbol parsing, vendor payload normalization, and guarantees
interoperability with the existing Step 3 point-in-time universe.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional, Union
import pandas as pd

from data.realtime.models import MarketSessionState, NormalizedSymbol, RealtimeQuote


class SymbolNormalizer:
    """
    Normalizes Indian equity symbol strings into standard canonical representation:
    '<EXCHANGE>:<TICKER>' (e.g. 'NSE:RELIANCE').
    """

    @staticmethod
    def normalize(symbol: str, default_exchange: str = "NSE") -> NormalizedSymbol:
        """
        Parse raw symbol string into NormalizedSymbol.
        
        Handles:
          - 'RELIANCE' -> NormalizedSymbol(ticker='RELIANCE', exchange='NSE')
          - 'RELIANCE.NS' -> NormalizedSymbol(ticker='RELIANCE', exchange='NSE')
          - 'TCS.BO' -> NormalizedSymbol(ticker='TCS', exchange='BSE')
          - 'NSE:INFY' -> NormalizedSymbol(ticker='INFY', exchange='NSE')
          - 'BSE:HDFCBANK' -> NormalizedSymbol(ticker='HDFCBANK', exchange='BSE')
        """
        if not symbol or not isinstance(symbol, str):
            raise ValueError(f"Symbol must be a non-empty string, got: {type(symbol)}")

        clean = symbol.strip().upper()
        if not clean:
            raise ValueError("Symbol cannot be empty or whitespace.")

        exchange = default_exchange.upper().strip()
        ticker = clean

        if ":" in clean:
            parts = clean.split(":", 1)
            exchange = parts[0].strip()
            ticker = parts[1].strip()
        elif clean.endswith(".NS"):
            exchange = "NSE"
            ticker = clean[:-3]
        elif clean.endswith(".BO"):
            exchange = "BSE"
            ticker = clean[:-3]

        return NormalizedSymbol(ticker=ticker, exchange=exchange)

    @staticmethod
    def to_canonical(symbol: str, default_exchange: str = "NSE") -> str:
        """Return canonical string directly e.g. 'NSE:RELIANCE'."""
        return SymbolNormalizer.normalize(symbol, default_exchange).canonical

    @staticmethod
    def to_ticker(canonical: str) -> str:
        """Extract plain ticker symbol for universe matching (e.g. 'NSE:RELIANCE' -> 'RELIANCE')."""
        return SymbolNormalizer.normalize(canonical).ticker

    @staticmethod
    def is_valid(symbol: str) -> bool:
        """Check whether a symbol string can be successfully normalized."""
        try:
            SymbolNormalizer.normalize(symbol)
            return True
        except (ValueError, TypeError):
            return False


class QuoteNormalizer:
    """
    Translates heterogeneous vendor or mock socket feeds into canonical RealtimeQuote instances.
    """

    @staticmethod
    def _parse_timestamp(ts: Any) -> datetime:
        """Ensure timestamp is valid datetime in UTC."""
        if isinstance(ts, datetime):
            if ts.tzinfo is None:
                return ts.replace(tzinfo=timezone.utc)
            return ts.astimezone(timezone.utc)
        if isinstance(ts, (int, float)):
            # Epoch timestamp (seconds or milliseconds)
            if ts > 1e11:  # ms
                return datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc)
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        if isinstance(ts, str):
            dt = pd.to_datetime(ts, utc=True)
            return dt.to_pydatetime()
        return datetime.now(timezone.utc)

    @classmethod
    def normalize_vendor_quote(
        cls,
        raw_data: Dict[str, Any],
        data_source: str = "GENERIC",
        default_exchange: str = "NSE",
    ) -> RealtimeQuote:
        """
        Normalize vendor dictionary into standard RealtimeQuote.
        
        Supports:
          1. Generic dictionary (symbol, last_price, volume, timestamp, bid, ask, ohlc)
          2. Zerodha Kite Ticker format (tradingsymbol, last_price, volume_traded, ohlc, depth)
        """
        # Symbol resolution
        raw_sym = (
            raw_data.get("symbol")
            or raw_data.get("tradingsymbol")
            or raw_data.get("ticker")
        )
        if not raw_sym:
            raise ValueError("Raw quote data missing 'symbol' or 'tradingsymbol' identifier.")

        norm_sym = SymbolNormalizer.normalize(raw_sym, default_exchange=default_exchange)

        # Price resolution
        last_price = raw_data.get("last_price")
        if last_price is None:
            last_price = raw_data.get("price") or raw_data.get("ltp")
        if last_price is None:
            raise ValueError(f"Quote for {norm_sym} missing price field.")
        last_price = float(last_price)

        # Volume resolution
        vol = (
            raw_data.get("volume")
            or raw_data.get("volume_traded")
            or raw_data.get("total_volume")
            or 0.0
        )
        volume = float(vol)

        # Timestamp resolution
        raw_ts = (
            raw_data.get("timestamp")
            or raw_data.get("last_trade_time")
            or raw_data.get("exchange_timestamp")
        )
        timestamp = cls._parse_timestamp(raw_ts)

        # Bid/Ask resolution
        bid = raw_data.get("bid") or raw_data.get("best_bid")
        ask = raw_data.get("ask") or raw_data.get("best_ask")

        # Kite depth structure support
        depth = raw_data.get("depth")
        if depth and isinstance(depth, dict):
            buy_depth = depth.get("buy", [])
            if buy_depth and isinstance(buy_depth, list) and len(buy_depth) > 0:
                bid = float(buy_depth[0].get("price", 0.0)) or bid
            sell_depth = depth.get("sell", [])
            if sell_depth and isinstance(sell_depth, list) and len(sell_depth) > 0:
                ask = float(sell_depth[0].get("price", 0.0)) or ask

        # OHLC resolution
        ohlc = raw_data.get("ohlc") or {}
        open_px = raw_data.get("open") or ohlc.get("open")
        high_px = raw_data.get("high") or ohlc.get("high")
        low_px = raw_data.get("low") or ohlc.get("low")
        prev_close = (
            raw_data.get("previous_close")
            or raw_data.get("prev_close")
            or ohlc.get("close")
        )

        # Provider timestamp & sequence number
        provider_ts = raw_data.get("provider_timestamp")
        p_timestamp = cls._parse_timestamp(provider_ts) if provider_ts else None
        seq_num = raw_data.get("sequence_number") or raw_data.get("seq_no")

        return RealtimeQuote(
            symbol=norm_sym.canonical,
            exchange=norm_sym.exchange,
            timestamp=timestamp,
            last_price=last_price,
            volume=volume,
            bid=float(bid) if bid is not None else None,
            ask=float(ask) if ask is not None else None,
            open=float(open_px) if open_px is not None else None,
            high=float(high_px) if high_px is not None else None,
            low=float(low_px) if low_px is not None else None,
            previous_close=float(prev_close) if prev_close is not None else None,
            provider_timestamp=p_timestamp,
            sequence_number=int(seq_num) if seq_num is not None else None,
            data_source=data_source,
            market_session_state=raw_data.get("market_session_state", MarketSessionState.REGULAR),
            metadata=dict(raw_data.get("metadata", {})),
        )

    @classmethod
    def normalize_kite_tick(cls, raw_data: Dict[str, Any]) -> RealtimeQuote:
        """Convenience adapter to normalize a Kite Ticker dictionary."""
        return cls.normalize_vendor_quote(raw_data, data_source="KITE")
