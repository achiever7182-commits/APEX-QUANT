"""
data/realtime/health.py — Feed Quality Monitoring & Market Session Telemetry.

Computes throughput metrics, tracks staleness across active symbols, and integrates
with NSEMarketCalendar to accurately reflect exchange trading status.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from data.market.calendar import NSEMarketCalendar, NSE_MARKET_OPEN, NSE_MARKET_CLOSE, NSE_PREMARKET_OPEN, IST_ZONE
from data.realtime.cache import LatestQuoteCache
from data.realtime.models import ConnectionState, FeedHealthMetrics, MarketSessionState


class FeedHealthMonitor:
    """
    Monitors data feed quality, connection states, and NSE market trading hours.
    """

    def __init__(self, calendar: Optional[NSEMarketCalendar] = None):
        self.calendar: NSEMarketCalendar = calendar or NSEMarketCalendar()
        self.metrics: FeedHealthMetrics = FeedHealthMetrics()

    def get_market_session_state(self, dt: Optional[datetime] = None) -> MarketSessionState:
        """
        Evaluate current official NSE session according to trading calendar.
        """
        ref = dt or datetime.now(timezone.utc)
        ist_now = ref.astimezone(IST_ZONE) if ref.tzinfo else ref.replace(tzinfo=timezone.utc).astimezone(IST_ZONE)
        curr_date = ist_now.date()

        # Check weekend
        if curr_date.weekday() >= 5:
            return MarketSessionState.WEEKEND

        # Check holiday
        if not self.calendar.is_trading_day(curr_date):
            return MarketSessionState.HOLIDAY

        curr_time = ist_now.time()
        if curr_time < NSE_PREMARKET_OPEN:
            return MarketSessionState.CLOSED
        if NSE_PREMARKET_OPEN <= curr_time < NSE_MARKET_OPEN:
            return MarketSessionState.PRE_MARKET
        if NSE_MARKET_OPEN <= curr_time <= NSE_MARKET_CLOSE:
            return MarketSessionState.REGULAR
        return MarketSessionState.POST_MARKET

    def record_message_received(self) -> None:
        self.metrics.messages_received += 1
        self.metrics.last_receive_timestamp = datetime.now(timezone.utc).isoformat()

    def record_message_valid(self, event_time: Optional[datetime] = None) -> None:
        self.metrics.valid_messages += 1
        if event_time:
            self.metrics.last_event_timestamp = event_time.isoformat()

    def record_message_invalid(self, category: Optional[str] = None) -> None:
        self.metrics.invalid_messages += 1
        if category == "DUPLICATE_EVENT":
            self.metrics.duplicate_messages += 1

    def record_message_dropped(self) -> None:
        self.metrics.dropped_messages += 1

    def record_reconnect(self) -> None:
        self.metrics.reconnect_count += 1

    def record_connection_state(self, state: ConnectionState) -> None:
        self.metrics.connection_state = state

    def record_subscriptions(self, count: int) -> None:
        self.metrics.subscribed_symbols_count = count

    def get_health_summary(
        self,
        cache: Optional[LatestQuoteCache] = None,
        max_staleness_seconds: float = 300.0,
        as_of: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Generate comprehensive operational health snapshot.
        """
        ref_t = as_of or datetime.now(timezone.utc)
        session = self.get_market_session_state(ref_t)

        stale_symbols: List[str] = []
        fresh_symbols: List[str] = []

        if cache is not None:
            for sym in cache.get_symbols():
                if cache.is_stale(sym, max_staleness_seconds=max_staleness_seconds, as_of=ref_t):
                    stale_symbols.append(sym)
                else:
                    fresh_symbols.append(sym)

        self.metrics.stale_symbols_count = len(stale_symbols)

        # High-level operational status
        if self.metrics.connection_state == ConnectionState.CONNECTED:
            if len(stale_symbols) > 0 and len(fresh_symbols) == 0 and len(stale_symbols) > 0:
                overall_status = "STALE"
            elif len(stale_symbols) > 0:
                overall_status = "DEGRADED"
            else:
                overall_status = "HEALTHY"
        elif self.metrics.connection_state in (ConnectionState.CONNECTING, ConnectionState.RECONNECTING):
            overall_status = "CONNECTING"
        else:
            overall_status = "DISCONNECTED"

        return {
            "overall_status": overall_status,
            "connection_state": self.metrics.connection_state.value,
            "market_session": session.value,
            "is_market_open": session == MarketSessionState.REGULAR,
            "subscribed_symbols_count": self.metrics.subscribed_symbols_count,
            "cached_symbols_count": len(cache) if cache else 0,
            "fresh_symbols_count": len(fresh_symbols),
            "stale_symbols_count": len(stale_symbols),
            "stale_symbols": stale_symbols,
            "messages_received": self.metrics.messages_received,
            "valid_messages": self.metrics.valid_messages,
            "invalid_messages": self.metrics.invalid_messages,
            "duplicate_messages": self.metrics.duplicate_messages,
            "dropped_messages": self.metrics.dropped_messages,
            "reconnect_count": self.metrics.reconnect_count,
            "last_receive_timestamp": self.metrics.last_receive_timestamp,
            "last_event_timestamp": self.metrics.last_event_timestamp,
        }


_global_health_monitor: Optional[FeedHealthMonitor] = None
_global_health_lock = threading.Lock()


def get_global_health_monitor() -> FeedHealthMonitor:
    """Return singleton instance of FeedHealthMonitor."""
    global _global_health_monitor
    with _global_health_lock:
        if _global_health_monitor is None:
            _global_health_monitor = FeedHealthMonitor()
        return _global_health_monitor
