"""
execution/broker.py — Abstract Broker Interface for APEX QUANT Execution Subsystem.

Defines the pluggable Broker interface enabling seamless transition between
paper simulation and future broker adapters without leaking execution details.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from execution.models import (
    BrokerCapabilities,
    BrokerConnectionState,
    OrderStatus,
    PaperAccount,
    PaperFill,
    PaperOrder,
    PaperPosition,
)


class Broker(ABC):
    """Abstract base broker interface."""

    @abstractmethod
    def submit_order(self, order: PaperOrder) -> PaperOrder:
        """
        Submit an order for execution.

        Returns:
            The order object updated with status, timestamps, and fill progress.
        """
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open/unfilled order. Returns True if cancelled."""
        pass

    @abstractmethod
    def get_order(self, order_id: str) -> Optional[PaperOrder]:
        """Retrieve an order by ID."""
        pass

    @abstractmethod
    def get_orders(self, status: Optional[OrderStatus] = None) -> List[PaperOrder]:
        """Retrieve historical or open orders, optionally filtered by status."""
        pass

    @abstractmethod
    def get_positions(self) -> Dict[str, PaperPosition]:
        """Retrieve current open positions mapped by symbol."""
        pass

    @abstractmethod
    def get_account(self) -> PaperAccount:
        """Retrieve current account equity, cash balance, and telemetry."""
        pass

    @abstractmethod
    def get_fills(self, order_id: Optional[str] = None) -> List[PaperFill]:
        """Retrieve execution fills, optionally filtered by order_id."""
        pass

    @abstractmethod
    def get_quote(self, symbol: str) -> Optional[float]:
        """Retrieve the latest market quote for a symbol."""
        pass

    @abstractmethod
    def reconcile(self) -> Dict[str, Any]:
        """Audit and compare broker internal accounting and positions."""
        pass

    @abstractmethod
    def get_capabilities(self) -> BrokerCapabilities:
        """Return the explicit capability matrix supported by this broker."""
        pass

    @abstractmethod
    def get_connection_status(self) -> BrokerConnectionState:
        """Return the current connection status to the broker."""
        pass

