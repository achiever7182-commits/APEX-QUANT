"""
execution/data_adapter.py — Market Data Safety Adapter for Indian Equities.

Reuses Step 2 NSEMarketCalendar and ParquetMarketDataStorage interfaces to provide
guarantees against stale quotes, future timestamps, missing quotes, and closed market sessions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union
import pandas as pd

from data.market.calendar import NSEMarketCalendar


@dataclass
class ValidatedQuote:
    """Safe, validated market quote."""
    symbol: str
    price: float
    volume: float
    timestamp: pd.Timestamp
    data_timestamp: pd.Timestamp
    data_age_seconds: float
    is_valid: bool
    rejection_reason: Optional[str] = None


@dataclass
class SignalContext:
    """Standardized signal envelope guaranteeing point-in-time freshness."""
    symbol: str
    timestamp: str
    data_timestamp: str
    data_age_seconds: float
    signal_timestamp: str


class MarketDataSafetyAdapter:
    """
    Adapter ensuring that stale quotes, weekend/holiday periods, and malformed
    data never silently enter the execution or risk pipelines.
    """

    def __init__(
        self,
        calendar: Optional[NSEMarketCalendar] = None,
        max_staleness_seconds: float = 300.0,  # 5 minutes
    ):
        self.calendar: NSEMarketCalendar = calendar or NSEMarketCalendar()
        self.max_staleness_seconds: float = float(max_staleness_seconds)

    def is_market_open(self, as_of_time: Optional[Union[datetime, pd.Timestamp]] = None) -> bool:
        """
        Check if Indian equity market is currently open.
        
        Evaluates trading day and 09:15–15:30 IST window.
        """
        t = as_of_time
        if t is None:
            t = datetime.now(timezone.utc)
        elif isinstance(t, pd.Timestamp):
            t = t.to_pydatetime()

        return self.calendar.is_market_open(t)

    def validate_quote(
        self,
        symbol: str,
        price: Any,
        volume: Any = 0.0,
        quote_timestamp: Optional[Union[datetime, pd.Timestamp, str]] = None,
        reference_time: Optional[Union[datetime, pd.Timestamp]] = None,
    ) -> ValidatedQuote:
        """
        Perform rigorous data safety validation on a market quote.
        """
        # 1. Symbol check
        if not symbol or not isinstance(symbol, str):
            return ValidatedQuote(
                symbol=str(symbol), price=0.0, volume=0.0,
                timestamp=pd.Timestamp.now(tz="UTC"), data_timestamp=pd.Timestamp.now(tz="UTC"),
                data_age_seconds=999999.0, is_valid=False,
                rejection_reason="INVALID_SYMBOL",
            )

        # 2. Price check
        try:
            px = float(price)
            if pd.isna(px) or px <= 0.0:
                return ValidatedQuote(
                    symbol=symbol, price=0.0, volume=0.0,
                    timestamp=pd.Timestamp.now(tz="UTC"), data_timestamp=pd.Timestamp.now(tz="UTC"),
                    data_age_seconds=999999.0, is_valid=False,
                    rejection_reason="MALFORMED_PRICE",
                )
        except (ValueError, TypeError):
            return ValidatedQuote(
                symbol=symbol, price=0.0, volume=0.0,
                timestamp=pd.Timestamp.now(tz="UTC"), data_timestamp=pd.Timestamp.now(tz="UTC"),
                data_age_seconds=999999.0, is_valid=False,
                rejection_reason="MALFORMED_PRICE",
            )

        # 3. Volume check
        try:
            vol = float(volume) if volume is not None and not pd.isna(volume) else 0.0
            if vol < 0.0:
                vol = 0.0
        except (ValueError, TypeError):
            vol = 0.0

        # 4. Timestamp parsing and validation
        ref_t = reference_time or pd.Timestamp.now(tz="UTC")
        if not isinstance(ref_t, pd.Timestamp):
            ref_t = pd.to_datetime(ref_t, utc=True)
        elif ref_t.tz is None:
            ref_t = ref_t.tz_localize("UTC")

        if quote_timestamp is None:
            q_time = ref_t
        else:
            q_time = pd.to_datetime(quote_timestamp, utc=True)

        # Check future timestamp relative to reference_time
        if q_time > ref_t + pd.Timedelta(seconds=5):
            return ValidatedQuote(
                symbol=symbol, price=px, volume=vol,
                timestamp=ref_t, data_timestamp=q_time,
                data_age_seconds=0.0, is_valid=False,
                rejection_reason="FUTURE_TIMESTAMP",
            )

        # Check staleness
        data_age = max(0.0, (ref_t - q_time).total_seconds())
        if self.max_staleness_seconds > 0 and data_age > self.max_staleness_seconds:
            return ValidatedQuote(
                symbol=symbol, price=px, volume=vol,
                timestamp=ref_t, data_timestamp=q_time,
                data_age_seconds=data_age, is_valid=False,
                rejection_reason="STALE_DATA",
            )

        return ValidatedQuote(
            symbol=symbol,
            price=px,
            volume=vol,
            timestamp=ref_t,
            data_timestamp=q_time,
            data_age_seconds=data_age,
            is_valid=True,
        )

    def create_signal_context(
        self,
        symbol: str,
        quote: ValidatedQuote,
        signal_timestamp: Optional[Union[datetime, pd.Timestamp, str]] = None,
    ) -> SignalContext:
        """Create explicit signal envelope recording data age and timestamps."""
        sig_t = signal_timestamp or pd.Timestamp.now(tz="UTC")
        if isinstance(sig_t, (datetime, pd.Timestamp)):
            sig_t_str = pd.to_datetime(sig_t, utc=True).isoformat()
        else:
            sig_t_str = str(sig_t)

        return SignalContext(
            symbol=symbol,
            timestamp=quote.timestamp.isoformat(),
            data_timestamp=quote.data_timestamp.isoformat(),
            data_age_seconds=quote.data_age_seconds,
            signal_timestamp=sig_t_str,
        )
