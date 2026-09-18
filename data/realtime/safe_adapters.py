"""
data/realtime/safe_adapters.py — Safe Upstream Broker Market Data Feed Adapter Stubs.

Provides architectural integration stubs for Indian broker market data feeds
(e.g., Zerodha Kite Ticker) while enforcing strict safety gates that block live network connections.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Sequence
from data.realtime.cache import LatestQuoteCache
from data.realtime.exceptions import (
    MarketDataConnectionError,
    MarketDataSubscriptionError,
)
from data.realtime.health import FeedHealthMonitor
from data.realtime.models import ConnectionState, RealtimeQuote
from data.realtime.normalizer import QuoteNormalizer, SymbolNormalizer
from data.realtime.provider import RealTimeMarketDataProvider
from data.realtime.reconnect import ConnectionManager
from data.realtime.validator import RealtimeDataValidator

logger = logging.getLogger("apex_quant.realtime.adapters")


class KiteRealTimeFeedAdapter(RealTimeMarketDataProvider):
    """
    Zerodha Kite Connect Ticker WebSocket Adapter Stub.
    
    Demonstrates protocol translation and binary packet decoding architecture,
    while gating live network sockets in Step 11.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        access_token: Optional[str] = None,
        mock_mode: bool = False,
        max_staleness_seconds: float = 300.0,
    ):
        self.api_key: Optional[str] = api_key
        self.access_token: Optional[str] = access_token
        self.mock_mode: bool = mock_mode
        self.max_staleness_seconds: float = float(max_staleness_seconds)

        self.cache = LatestQuoteCache()
        self.validator = RealtimeDataValidator()
        self.connection_manager = ConnectionManager(max_attempts=5)
        self.health_monitor = FeedHealthMonitor()
        self.subscribed_symbols: Dict[str, str] = {}
        self.callbacks: List[Callable[[RealtimeQuote], None]] = []

    def connect(self) -> bool:
        """
        Connect to data feed.
        
        SAFETY GATE: Live socket connection is disabled in Step 11.
        Throws MarketDataConnectionError if mock_mode=False.
        """
        if not self.mock_mode:
            self.connection_manager.state = ConnectionState.FAILED
            self.health_monitor.record_connection_state(ConnectionState.FAILED)
            raise MarketDataConnectionError(
                "Live Kite Ticker streaming is disabled in Step 11. "
                "Real external broker network connections are strictly blocked.",
                provider_name="KiteRealTimeFeedAdapter",
            )

        self.connection_manager.record_connecting()
        self.connection_manager.record_success()
        self.health_monitor.record_connection_state(ConnectionState.CONNECTED)
        logger.info("[KiteRealTimeFeedAdapter] Connected in mock/safe mode.")
        return True

    def disconnect(self) -> None:
        self.connection_manager.record_disconnect()
        self.health_monitor.record_connection_state(ConnectionState.DISCONNECTED)
        logger.info("[KiteRealTimeFeedAdapter] Disconnected.")

    def subscribe(self, symbols: Sequence[str]) -> List[str]:
        if not self.is_connected():
            raise MarketDataConnectionError("Cannot subscribe while disconnected", provider_name="KiteRealTimeFeedAdapter")

        subscribed: List[str] = []
        for s in symbols:
            if SymbolNormalizer.is_valid(s):
                can = SymbolNormalizer.to_canonical(s)
                self.subscribed_symbols[can] = can
                subscribed.append(can)

        self.health_monitor.record_subscriptions(len(self.subscribed_symbols))
        return subscribed

    def unsubscribe(self, symbols: Sequence[str]) -> List[str]:
        unsubscribed: List[str] = []
        for s in symbols:
            if SymbolNormalizer.is_valid(s):
                can = SymbolNormalizer.to_canonical(s)
                if can in self.subscribed_symbols:
                    del self.subscribed_symbols[can]
                    unsubscribed.append(can)

        self.health_monitor.record_subscriptions(len(self.subscribed_symbols))
        return unsubscribed

    def get_latest(self, symbol: str) -> Optional[RealtimeQuote]:
        return self.cache.get_latest(symbol)

    def get_snapshot(self) -> Dict[str, RealtimeQuote]:
        return self.cache.get_all_latest()

    def get_health(self) -> Dict[str, Any]:
        return self.health_monitor.get_health_summary(
            cache=self.cache,
            max_staleness_seconds=self.max_staleness_seconds,
        )

    def get_connection_state(self) -> ConnectionState:
        return self.connection_manager.state

    def is_connected(self) -> bool:
        return self.connection_manager.state == ConnectionState.CONNECTED

    def get_subscribed_symbols(self) -> List[str]:
        return list(self.subscribed_symbols.keys())

    def register_callback(self, callback: Callable[[RealtimeQuote], None]) -> None:
        self.callbacks.append(callback)

    def process_incoming_packet(self, packet: Dict[str, Any]) -> Optional[RealtimeQuote]:
        """
        Process a vendor tick packet (used in mock/test replay mode).
        """
        self.health_monitor.record_message_received()
        try:
            quote = QuoteNormalizer.normalize_vendor_quote(packet, data_source="KITE_TICKER")
        except Exception as e:
            self.health_monitor.record_message_invalid("PARSE_ERROR")
            return None

        val_res = self.validator.validate(quote)
        if not val_res.is_valid:
            self.health_monitor.record_message_invalid(val_res.rejection_category)
            return None

        updated = self.cache.update(quote)
        if not updated:
            self.health_monitor.record_message_invalid("TIMESTAMP_REGRESSION")
            return None

        self.health_monitor.record_message_valid(event_time=quote.timestamp)

        for cb in self.callbacks:
            try:
                cb(quote)
            except Exception:
                pass

        return quote
