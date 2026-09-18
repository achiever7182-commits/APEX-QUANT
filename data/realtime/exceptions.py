"""
data/realtime/exceptions.py — Strongly Typed Market Data Exception Hierarchy.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


class MarketDataError(Exception):
    """Base exception for all real-time market data errors."""

    def __init__(self, message: str, provider_name: str = "Unknown", details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.provider_name = provider_name
        self.details = details or {}

    def __str__(self) -> str:
        return f"[{self.provider_name}] {self.message}"


class MarketDataConnectionError(MarketDataError):
    """Raised when market data connection fails, drops, or exhausts retries."""
    pass


class MarketDataValidationError(MarketDataError):
    """Raised when incoming market data violates validation invariants."""
    pass


class MarketDataStaleError(MarketDataError):
    """Raised when quote or market feed exceeds allowable staleness."""
    pass


class MarketDataProviderError(MarketDataError):
    """Raised on upstream provider failure or rejected request."""
    pass


class MarketDataSubscriptionError(MarketDataError):
    """Raised when symbol subscription fails or symbol limit is exceeded."""
    pass
