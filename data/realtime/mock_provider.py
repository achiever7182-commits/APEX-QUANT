"""
data/realtime/mock_provider.py — Deterministic Mock Real-Time Market Data Provider.

Simulates live Indian equity feeds with controllable random seed, realistic drift,
deterministic multi-symbol streaming, and explicit fault injection hooks for testing.
"""

from __future__ import annotations

import random
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence
from data.market.calendar import NSEMarketCalendar
from data.realtime.cache import LatestQuoteCache
from data.realtime.exceptions import (
    MarketDataConnectionError,
    MarketDataSubscriptionError,
)
from data.realtime.health import FeedHealthMonitor
from data.realtime.models import (
    ConnectionState,
    MarketSessionState,
    RealtimeQuote,
)
from data.realtime.normalizer import SymbolNormalizer
from data.realtime.provider import RealTimeMarketDataProvider
from data.realtime.reconnect import ConnectionManager
from data.realtime.validator import RealtimeDataValidator

DEFAULT_BASE_PRICES = {
    "NSE:RELIANCE": 2850.0,
    "NSE:TCS": 3900.0,
    "NSE:INFY": 1500.0,
    "NSE:HDFCBANK": 1650.0,
    "NSE:ICICIBANK": 1100.0,
}


class MockRealTimeProvider(RealTimeMarketDataProvider):
    """
    Deterministic simulated real-time data provider.
    
    Generates synthetic price movements, bid/ask spreads, and volume updates
    strictly without external networking.
    """

    def __init__(
        self,
        seed: int = 42,
        base_prices: Optional[Dict[str, float]] = None,
        max_symbols: int = 500,
        max_staleness_seconds: float = 300.0,
        calendar: Optional[NSEMarketCalendar] = None,
    ):
        self.rng = random.Random(seed)
        self.max_symbols = max_symbols
        self.max_staleness_seconds = float(max_staleness_seconds)
        self.prices: Dict[str, float] = dict(base_prices or DEFAULT_BASE_PRICES)

        # Session OHLC tracker
        self.session_ohlc: Dict[str, Dict[str, float]] = {}
        for sym, px in self.prices.items():
            self.session_ohlc[sym] = {"open": px, "high": px, "low": px, "close": px, "volume": 1000.0}

        self.cache = LatestQuoteCache()
        self.validator = RealtimeDataValidator()
        self.connection_manager = ConnectionManager(max_attempts=5, base_delay_seconds=1.0)
        self.health_monitor = FeedHealthMonitor(calendar=calendar)
        self.subscribed_symbols: Dict[str, str] = {}
        self.callbacks: List[Callable[[RealtimeQuote], None]] = []
        self._sequence_counter: Dict[str, int] = {}

    def connect(self) -> bool:
        """Connect mock provider."""
        self.connection_manager.record_connecting()
        self.health_monitor.record_connection_state(ConnectionState.CONNECTING)

        self.connection_manager.record_success()
        self.health_monitor.record_connection_state(ConnectionState.CONNECTED)
        return True

    def disconnect(self) -> None:
        """Disconnect mock provider."""
        self.connection_manager.record_disconnect()
        self.health_monitor.record_connection_state(ConnectionState.DISCONNECTED)

    def subscribe(self, symbols: Sequence[str]) -> List[str]:
        """Subscribe to a list of symbols."""
        if not self.is_connected():
            raise MarketDataConnectionError("Cannot subscribe while disconnected", provider_name="MockRealTimeProvider")

        subscribed: List[str] = []
        for s in symbols:
            if not SymbolNormalizer.is_valid(s):
                continue
            canonical = SymbolNormalizer.to_canonical(s)
            if len(self.subscribed_symbols) >= self.max_symbols and canonical not in self.subscribed_symbols:
                raise MarketDataSubscriptionError(
                    f"Exceeded max subscription limit of {self.max_symbols} symbols",
                    provider_name="MockRealTimeProvider",
                )
            self.subscribed_symbols[canonical] = canonical
            if canonical not in self.prices:
                self.prices[canonical] = 1000.0
                self.session_ohlc[canonical] = {
                    "open": 1000.0, "high": 1000.0, "low": 1000.0, "close": 1000.0, "volume": 1000.0
                }
            subscribed.append(canonical)

        self.health_monitor.record_subscriptions(len(self.subscribed_symbols))
        return subscribed

    def unsubscribe(self, symbols: Sequence[str]) -> List[str]:
        """Unsubscribe from symbols."""
        unsubscribed: List[str] = []
        for s in symbols:
            if SymbolNormalizer.is_valid(s):
                canonical = SymbolNormalizer.to_canonical(s)
                if canonical in self.subscribed_symbols:
                    del self.subscribed_symbols[canonical]
                    unsubscribed.append(canonical)

        self.health_monitor.record_subscriptions(len(self.subscribed_symbols))
        return unsubscribed

    def get_latest(self, symbol: str) -> Optional[RealtimeQuote]:
        """Query latest quote from cache."""
        return self.cache.get_latest(symbol)

    def get_snapshot(self) -> Dict[str, RealtimeQuote]:
        """Return all latest cached quotes."""
        return self.cache.get_all_latest()

    def get_health(self) -> Dict[str, Any]:
        """Return operational health snapshot."""
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

    def _next_sequence(self, symbol: str) -> int:
        curr = self._sequence_counter.get(symbol, 0) + 1
        self._sequence_counter[symbol] = curr
        return curr

    def generate_tick(
        self,
        symbol: str,
        price: Optional[float] = None,
        volume_delta: Optional[float] = None,
        timestamp: Optional[datetime] = None,
        sequence_number: Optional[int] = None,
        bid: Optional[float] = None,
        ask: Optional[float] = None,
        data_source: str = "MOCK",
        market_session_state: MarketSessionState = MarketSessionState.REGULAR,
    ) -> Optional[RealtimeQuote]:
        """
        Generate and process a single deterministic tick for a symbol.
        """
        canonical = SymbolNormalizer.to_canonical(symbol)
        now_t = timestamp or datetime.now(timezone.utc)
        if now_t.tzinfo is None:
            now_t = now_t.replace(tzinfo=timezone.utc)

        self.health_monitor.record_message_received()

        # Compute price movement if not explicitly provided
        if price is None:
            curr_px = self.prices.get(canonical, 1000.0)
            drift = self.rng.uniform(-0.003, 0.003)
            price = round(curr_px * (1.0 + drift), 2)

        self.prices[canonical] = price

        # Update session OHLC
        ohlc = self.session_ohlc.setdefault(
            canonical, {"open": price, "high": price, "low": price, "close": price, "volume": 0.0}
        )
        if price > ohlc["high"]:
            ohlc["high"] = price
        if price < ohlc["low"]:
            ohlc["low"] = price
        ohlc["close"] = price
        vol_add = volume_delta if volume_delta is not None else float(self.rng.randint(10, 500))
        ohlc["volume"] += max(0.0, vol_add)

        # Compute bid/ask
        half_spread = round(price * 0.0002, 2)
        final_bid = bid if bid is not None else round(price - half_spread, 2)
        final_ask = ask if ask is not None else round(price + half_spread, 2)

        seq = sequence_number if sequence_number is not None else self._next_sequence(canonical)

        norm_sym = SymbolNormalizer.normalize(canonical)
        quote = RealtimeQuote(
            symbol=norm_sym.canonical,
            exchange=norm_sym.exchange,
            timestamp=now_t,
            last_price=price,
            volume=ohlc["volume"],
            bid=final_bid,
            ask=final_ask,
            open=ohlc["open"],
            high=ohlc["high"],
            low=ohlc["low"],
            previous_close=round(ohlc["open"] * 0.995, 2),
            provider_timestamp=now_t,
            sequence_number=seq,
            data_source=data_source,
            market_session_state=market_session_state,
        )

        # Validate quote
        val_res = self.validator.validate(quote, reference_time=now_t)
        if not val_res.is_valid:
            self.health_monitor.record_message_invalid(val_res.rejection_category)
            return None

        # Cache update
        updated = self.cache.update(quote)
        if not updated:
            self.health_monitor.record_message_invalid("TIMESTAMP_REGRESSION")
            return None

        self.health_monitor.record_message_valid(event_time=now_t)

        # Emit to callbacks
        for cb in self.callbacks:
            try:
                cb(quote)
            except Exception:
                pass

        return quote

    def generate_panel_ticks(self, timestamp: Optional[datetime] = None) -> List[RealtimeQuote]:
        """Generate a round of updates for all subscribed symbols."""
        quotes: List[RealtimeQuote] = []
        for sym in list(self.subscribed_symbols.keys()):
            q = self.generate_tick(sym, timestamp=timestamp)
            if q:
                quotes.append(q)
        return quotes

    # ── Test Fault Injection Hooks ──

    def inject_malformed_quote(self, symbol: str) -> None:
        """Inject negative price for testing validator."""
        self.generate_tick(symbol, price=-100.0)

    def inject_future_timestamp(self, symbol: str, seconds_ahead: float = 60.0) -> None:
        """Inject quote with clock-skew violation."""
        from datetime import timedelta
        future_t = datetime.now(timezone.utc) + timedelta(seconds=seconds_ahead)
        self.generate_tick(symbol, timestamp=future_t)

    def inject_stale_quote(self, symbol: str, seconds_old: float = 600.0) -> None:
        """Inject an old quote."""
        from datetime import timedelta
        old_t = datetime.now(timezone.utc) - timedelta(seconds=seconds_old)
        self.generate_tick(symbol, timestamp=old_t)

    def inject_duplicate_sequence(self, symbol: str) -> None:
        """Inject duplicate sequence number."""
        canonical = SymbolNormalizer.to_canonical(symbol)
        last_seq = self._sequence_counter.get(canonical, 1)
        self.generate_tick(symbol, sequence_number=last_seq)

    def inject_out_of_order_sequence(self, symbol: str) -> None:
        """Inject out-of-order sequence number."""
        canonical = SymbolNormalizer.to_canonical(symbol)
        curr = self._sequence_counter.get(canonical, 10)
        self.generate_tick(symbol, sequence_number=max(1, curr - 5))

    def inject_disconnect(self) -> None:
        """Simulate upstream socket break."""
        delay = self.connection_manager.record_failure()
        self.health_monitor.record_connection_state(self.connection_manager.state)
        self.health_monitor.record_reconnect()
