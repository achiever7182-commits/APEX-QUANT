"""
data/realtime/provider.py — Abstract Real-Time Market Data Provider Interface.

Defines the pluggable provider protocol enabling seamless interchange between
mock feeds, historical replays, and future live broker socket feeds.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Sequence
from data.realtime.models import ConnectionState, RealtimeQuote


class RealTimeMarketDataProvider(ABC):
    """
    Abstract base provider protocol for streaming real-time market data.
    """

    @abstractmethod
    def connect(self) -> bool:
        """Establish connection or session with market data source."""
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Terminate connection and release resources."""
        pass

    @abstractmethod
    def subscribe(self, symbols: Sequence[str]) -> List[str]:
        """
        Subscribe to real-time quotes for given list of symbols.
        Returns list of successfully subscribed canonical symbols.
        """
        pass

    @abstractmethod
    def unsubscribe(self, symbols: Sequence[str]) -> List[str]:
        """
        Unsubscribe from real-time quotes.
        Returns list of successfully unsubscribed canonical symbols.
        """
        pass

    @abstractmethod
    def get_latest(self, symbol: str) -> Optional[RealtimeQuote]:
        """Retrieve most recent validated quote for symbol."""
        pass

    @abstractmethod
    def get_snapshot(self) -> Dict[str, RealtimeQuote]:
        """Retrieve snapshot of all latest subscribed quotes."""
        pass

    @abstractmethod
    def get_health(self) -> Dict[str, Any]:
        """Retrieve operational health summary and metrics."""
        pass

    @abstractmethod
    def get_connection_state(self) -> ConnectionState:
        """Return current connection state."""
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """Return True if connection state is CONNECTED."""
        pass

    @abstractmethod
    def get_subscribed_symbols(self) -> List[str]:
        """Return list of currently subscribed canonical symbols."""
        pass

    @abstractmethod
    def register_callback(self, callback: Callable[[RealtimeQuote], None]) -> None:
        """Register a callback for streaming quote updates."""
        pass
