"""
execution/exceptions.py — Strongly Typed Broker Exception Hierarchy.

Defines standard exceptions for external and simulated broker operations,
enabling explicit, fail-closed error handling across the execution layer.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


class BrokerError(Exception):
    """Base exception for all execution and broker errors."""

    def __init__(self, message: str, broker_name: str = "Unknown", details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message: str = message
        self.broker_name: str = broker_name
        self.details: Dict[str, Any] = details or {}

    def __str__(self) -> str:
        return f"[{self.broker_name}] {self.message}"


class BrokerConnectionError(BrokerError):
    """Raised when broker connection fails or disconnects unexpectedly."""
    pass


class BrokerTimeoutError(BrokerError):
    """Raised when a broker request times out before receiving a confirmation."""
    pass


class BrokerOrderRejectedError(BrokerError):
    """Raised when a broker explicitly rejects an order."""
    pass


class BrokerUncertainStateError(BrokerError):
    """
    Raised when order submission or cancellation returns an ambiguous result.
    
    Critical Safety Guard: The system MUST fail closed and NEVER blindly resubmit.
    """
    pass


class BrokerAuthenticationError(BrokerError):
    """Raised when broker API credentials, access token, or session fails authentication."""
    pass


class LiveTradingDisabledError(BrokerError):
    """Raised when live broker order execution is attempted in non-live or research modes."""
    pass
