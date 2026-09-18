"""
data/realtime/validator.py — Strict Real-Time Data Validation Engine.

Enforces zero silent mutations and strict mathematical and financial invariants:
  - Positive non-zero price
  - Non-negative volume
  - Valid timestamps without future clock-skew violation
  - Strict OHLC boundary relationships: low <= open/close <= high
  - Monotonic sequence checks
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional
import pandas as pd

from data.realtime.models import RealtimeQuote


@dataclass(frozen=True)
class ValidationResult:
    """Result of real-time quote validation check."""
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    quote: Optional[RealtimeQuote] = None
    rejection_category: Optional[str] = None

    def __bool__(self) -> bool:
        return self.is_valid


class RealtimeDataValidator:
    """
    Validates streaming market quotes against strict physical, mathematical,
    and exchange-timing rules.
    """

    def __init__(self, clock_skew_tolerance_seconds: float = 5.0):
        self.clock_skew_tolerance_seconds: float = float(clock_skew_tolerance_seconds)
        self._last_sequence_numbers: Dict[str, int] = {}

    def reset_sequence_tracking(self, symbol: Optional[str] = None) -> None:
        """Reset sequence tracker for testing or reconnect."""
        if symbol:
            self._last_sequence_numbers.pop(symbol, None)
        else:
            self._last_sequence_numbers.clear()

    def validate(
        self,
        quote: RealtimeQuote,
        reference_time: Optional[datetime] = None,
    ) -> ValidationResult:
        """
        Execute comprehensive validation pipeline on incoming quote.
        """
        errors: List[str] = []
        rejection_cat: Optional[str] = None

        # 1. Symbol structure check
        if not quote.symbol or ":" not in quote.symbol:
            errors.append(f"Malformed or non-canonical symbol: '{quote.symbol}'")
            return ValidationResult(
                is_valid=False,
                errors=errors,
                quote=quote,
                rejection_category="INVALID_SYMBOL",
            )

        # 2. Price validity checks (must be finite, positive, non-zero)
        if quote.last_price is None or math.isnan(quote.last_price) or math.isinf(quote.last_price):
            errors.append(f"last_price is NaN, Inf, or None for {quote.symbol}")
            rejection_cat = "MALFORMED_PRICE"
        elif quote.last_price <= 0.0:
            errors.append(f"Non-positive last_price {quote.last_price} for {quote.symbol}")
            rejection_cat = "NEGATIVE_PRICE" if quote.last_price < 0.0 else "ZERO_PRICE"

        # 3. Volume sanity checks
        if quote.volume is None or math.isnan(quote.volume) or math.isinf(quote.volume):
            errors.append(f"Volume is NaN or Inf for {quote.symbol}")
            rejection_cat = rejection_cat or "MALFORMED_VOLUME"
        elif quote.volume < 0.0:
            errors.append(f"Negative volume {quote.volume} for {quote.symbol}")
            rejection_cat = rejection_cat or "NEGATIVE_VOLUME"

        # 4. Timestamp sanity & Future Timestamp detection
        q_t = quote.timestamp
        if q_t is None or not isinstance(q_t, datetime):
            errors.append(f"Invalid timestamp '{q_t}' for {quote.symbol}")
            rejection_cat = rejection_cat or "INVALID_TIMESTAMP"
            return ValidationResult(is_valid=False, errors=errors, quote=None, rejection_category=rejection_cat)

        ref_t = reference_time or datetime.now(timezone.utc)
        if ref_t.tzinfo is None:
            ref_t = ref_t.replace(tzinfo=timezone.utc)
        else:
            ref_t = ref_t.astimezone(timezone.utc)

        if q_t.tzinfo is None:
            q_t = q_t.replace(tzinfo=timezone.utc)
        else:
            q_t = q_t.astimezone(timezone.utc)

        # Calculate time difference
        time_diff = (q_t - ref_t).total_seconds()
        if time_diff > self.clock_skew_tolerance_seconds:
            errors.append(
                f"Future timestamp detected: quote time {q_t.isoformat()} exceeds reference {ref_t.isoformat()} by {time_diff:.2f}s"
            )
            rejection_cat = rejection_cat or "FUTURE_TIMESTAMP"

        # 5. Bid / Ask consistency
        if quote.bid is not None and quote.ask is not None:
            if quote.bid <= 0.0 or quote.ask <= 0.0:
                errors.append(f"Bid/Ask prices must be strictly positive: bid={quote.bid}, ask={quote.ask}")
                rejection_cat = rejection_cat or "INVALID_BID_ASK"
            elif quote.bid > quote.ask:
                errors.append(f"Crossed market spread: bid ({quote.bid}) > ask ({quote.ask})")
                rejection_cat = rejection_cat or "CROSSED_SPREAD"

        # 6. Strict OHLC relational checks
        # Invariants: low <= open <= high and low <= close <= high and low <= high
        o = quote.open
        h = quote.high
        l = quote.low
        c = quote.last_price  # current/close price

        if h is not None and l is not None:
            if h < l:
                errors.append(f"High ({h}) < Low ({l}) for {quote.symbol}")
                rejection_cat = rejection_cat or "INVALID_OHLC"
            if o is not None:
                if o > h or o < l:
                    errors.append(f"Open ({o}) outside [Low={l}, High={h}] range for {quote.symbol}")
                    rejection_cat = rejection_cat or "INVALID_OHLC"
            if c > h or c < l:
                # Last price must respect day's high/low
                errors.append(f"Last price ({c}) outside [Low={l}, High={h}] range for {quote.symbol}")
                rejection_cat = rejection_cat or "INVALID_OHLC"

        # 7. Sequence number ordering and deduplication
        if quote.sequence_number is not None:
            last_seq = self._last_sequence_numbers.get(quote.symbol)
            if last_seq is not None:
                if quote.sequence_number == last_seq:
                    errors.append(f"Duplicate sequence number {quote.sequence_number} for {quote.symbol}")
                    rejection_cat = rejection_cat or "DUPLICATE_EVENT"
                elif quote.sequence_number < last_seq:
                    errors.append(
                        f"Out-of-order sequence number {quote.sequence_number} < last seen {last_seq} for {quote.symbol}"
                    )
                    rejection_cat = rejection_cat or "OUT_OF_ORDER_EVENT"

        if errors:
            return ValidationResult(
                is_valid=False,
                errors=errors,
                quote=quote,
                rejection_category=rejection_cat or "VALIDATION_FAILED",
            )

        # Update valid sequence tracking
        if quote.sequence_number is not None:
            self._last_sequence_numbers[quote.symbol] = quote.sequence_number

        return ValidationResult(is_valid=True, errors=[], quote=quote, rejection_category=None)
