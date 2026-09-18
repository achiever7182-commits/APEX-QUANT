"""
tests/test_realtime_market_data.py — Test Suite for Real-Time Indian Market Data Infrastructure.

Covers 30 comprehensive unit, integration, and safety boundary test cases for Step 11.
"""

from __future__ import annotations

import math
import os
import sys
import time
import unittest
from datetime import datetime, timedelta, timezone

# Ensure project root is in sys.path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from data.market.calendar import IST_ZONE, NSEMarketCalendar
from data.market.models import MarketBar
from data.realtime import (
    AggregatedBar,
    ConnectionManager,
    ConnectionState,
    FeedHealthMetrics,
    FeedHealthMonitor,
    HistoricalRealtimeHandoff,
    KiteRealTimeFeedAdapter,
    LatestQuoteCache,
    MarketDataConnectionError,
    MarketDataError,
    MarketDataProviderError,
    MarketDataStaleError,
    MarketDataSubscriptionError,
    MarketDataValidationError,
    MarketSessionState,
    MockRealTimeProvider,
    NormalizedSymbol,
    QuoteNormalizer,
    RealtimeBarAggregator,
    RealtimeConfig,
    RealTimeMarketDataProvider,
    RealtimeQuote,
    RealtimeDataValidator,
    SymbolNormalizer,
    ValidationResult,
    get_global_health_monitor,
    get_global_quote_cache,
)


class TestRealtimeMarketData(unittest.TestCase):
    """30 comprehensive tests for Step 11 Real-Time Market Data."""

    # 1. Provider Interface Compliance
    def test_01_provider_interface_compliance(self):
        mock_p = MockRealTimeProvider(seed=42)
        kite_p = KiteRealTimeFeedAdapter(mock_mode=True)
        self.assertIsInstance(mock_p, RealTimeMarketDataProvider)
        self.assertIsInstance(kite_p, RealTimeMarketDataProvider)

        # Verify all ABC methods exist
        for p in [mock_p, kite_p]:
            self.assertTrue(hasattr(p, "connect"))
            self.assertTrue(hasattr(p, "disconnect"))
            self.assertTrue(hasattr(p, "subscribe"))
            self.assertTrue(hasattr(p, "unsubscribe"))
            self.assertTrue(hasattr(p, "get_latest"))
            self.assertTrue(hasattr(p, "get_snapshot"))
            self.assertTrue(hasattr(p, "get_subscribed_symbols"))
            self.assertTrue(hasattr(p, "get_health"))
            self.assertTrue(hasattr(p, "get_connection_state"))
            self.assertTrue(hasattr(p, "is_connected"))

    # 2. Mock Connection Lifecycle
    def test_02_mock_connection_lifecycle(self):
        provider = MockRealTimeProvider(seed=101)
        self.assertEqual(provider.get_connection_state(), ConnectionState.DISCONNECTED)
        self.assertFalse(provider.is_connected())

        provider.connect()
        self.assertEqual(provider.get_connection_state(), ConnectionState.CONNECTED)
        self.assertTrue(provider.is_connected())

        provider.disconnect()
        self.assertEqual(provider.get_connection_state(), ConnectionState.DISCONNECTED)
        self.assertFalse(provider.is_connected())

    # 3. Subscription and Unsubscription
    def test_03_subscription_and_unsubscription(self):
        provider = MockRealTimeProvider()
        provider.connect()
        provider.subscribe(["RELIANCE", "TCS.NS", "NSE:INFY"])
        subs = provider.get_subscribed_symbols()
        self.assertIn("NSE:RELIANCE", subs)
        self.assertIn("NSE:TCS", subs)
        self.assertIn("NSE:INFY", subs)
        self.assertEqual(len(subs), 3)

        provider.unsubscribe(["TCS"])
        subs_after = provider.get_subscribed_symbols()
        self.assertNotIn("NSE:TCS", subs_after)
        self.assertEqual(len(subs_after), 2)
        provider.disconnect()

    # 4. Valid Quote Normalization
    def test_04_valid_quote_normalization(self):
        raw = {
            "instrument_token": 738561,
            "tradingsymbol": "RELIANCE",
            "last_price": 2850.50,
            "volume": 1250000,
            "buy_quantity": 500,
            "sell_quantity": 300,
            "ohlc": {"open": 2830.0, "high": 2870.0, "low": 2825.0, "close": 2840.0},
            "timestamp": datetime.now(timezone.utc),
            "depth": {
                "buy": [{"price": 2850.0, "quantity": 100}],
                "sell": [{"price": 2851.0, "quantity": 150}],
            },
        }
        quote = QuoteNormalizer.normalize_kite_tick(raw)
        self.assertEqual(quote.symbol, "NSE:RELIANCE")
        self.assertEqual(quote.exchange, "NSE")
        self.assertEqual(quote.last_price, 2850.50)
        self.assertEqual(quote.bid, 2850.0)
        self.assertEqual(quote.ask, 2851.0)
        self.assertEqual(quote.volume, 1250000)
        self.assertEqual(quote.open, 2830.0)
        self.assertEqual(quote.high, 2870.0)
        self.assertEqual(quote.low, 2825.0)

    # 5. Malformed Quote Rejection
    def test_05_malformed_quote_rejection(self):
        validator = RealtimeDataValidator()
        # Missing last_price or non-numeric
        bad_quote = RealtimeQuote(
            symbol="NSE:RELIANCE",
            exchange="NSE",
            timestamp=datetime.now(timezone.utc),
            last_price=float("nan"),
            volume=100.0,
        )
        res = validator.validate(bad_quote)
        self.assertFalse(res.is_valid)
        self.assertTrue(any("last_price" in err for err in res.errors))

    # 6. Negative or Zero Price Rejection
    def test_06_negative_or_zero_price_rejection(self):
        validator = RealtimeDataValidator()
        zero_quote = RealtimeQuote(
            symbol="NSE:INFY",
            exchange="NSE",
            timestamp=datetime.now(timezone.utc),
            last_price=0.0,
            volume=50.0,
        )
        neg_quote = RealtimeQuote(
            symbol="NSE:INFY",
            exchange="NSE",
            timestamp=datetime.now(timezone.utc),
            last_price=-150.0,
            volume=50.0,
        )
        self.assertFalse(validator.validate(zero_quote).is_valid)
        self.assertFalse(validator.validate(neg_quote).is_valid)

    # 7. Invalid OHLC Relationships Rejection
    def test_07_invalid_ohlc_relationships(self):
        validator = RealtimeDataValidator()
        # High less than Low
        bad_ohlc1 = RealtimeQuote(
            symbol="NSE:TCS",
            exchange="NSE",
            timestamp=datetime.now(timezone.utc),
            last_price=3500.0,
            volume=1000.0,
            open=3510.0,
            high=3400.0,  # high < low
            low=3450.0,
            close=3500.0,
        )
        # Open > High
        bad_ohlc2 = RealtimeQuote(
            symbol="NSE:TCS",
            exchange="NSE",
            timestamp=datetime.now(timezone.utc),
            last_price=3500.0,
            volume=1000.0,
            open=3600.0,  # open > high
            high=3550.0,
            low=3450.0,
            close=3500.0,
        )
        self.assertFalse(validator.validate(bad_ohlc1).is_valid)
        self.assertFalse(validator.validate(bad_ohlc2).is_valid)

    # 8. Invalid Timestamp Rejection
    def test_08_invalid_timestamp_rejection(self):
        validator = RealtimeDataValidator()
        bad_ts_quote = RealtimeQuote(
            symbol="NSE:RELIANCE",
            exchange="NSE",
            timestamp=None,  # type: ignore
            last_price=2800.0,
            volume=100.0,
        )
        res = validator.validate(bad_ts_quote)
        self.assertFalse(res.is_valid)
        self.assertTrue(any("timestamp" in err for err in res.errors))

    # 9. Future Timestamp Rejection
    def test_09_future_timestamp_rejection(self):
        validator = RealtimeDataValidator(clock_skew_tolerance_seconds=5.0)
        # Timestamp 60 seconds into future
        future_ts = datetime.now(timezone.utc) + timedelta(seconds=60)
        future_quote = RealtimeQuote(
            symbol="NSE:HDFCBANK",
            exchange="NSE",
            timestamp=future_ts,
            last_price=1600.0,
            volume=1000.0,
        )
        res = validator.validate(future_quote)
        self.assertFalse(res.is_valid)
        self.assertTrue(any("future" in err.lower() for err in res.errors))

    # 10. Stale Quote Detection
    def test_10_stale_quote_detection(self):
        cache = LatestQuoteCache()
        old_time = datetime.now(timezone.utc) - timedelta(seconds=600)
        q = RealtimeQuote(
            symbol="NSE:ICICIBANK",
            exchange="NSE",
            timestamp=old_time,
            last_price=1050.0,
            volume=5000.0,
        )
        cache.update(q)
        # With threshold 300 seconds, 600s old is stale
        self.assertTrue(cache.is_stale("NSE:ICICIBANK", max_staleness_seconds=300.0))
        # With threshold 1000 seconds, 600s old is not stale
        self.assertFalse(cache.is_stale("NSE:ICICIBANK", max_staleness_seconds=1000.0))

    # 11. Duplicate Event Handling
    def test_11_duplicate_event_handling(self):
        monitor = FeedHealthMonitor()
        monitor.record_message_received()
        monitor.record_message_invalid(category="DUPLICATE_EVENT")
        summary = monitor.get_health_summary()
        self.assertEqual(summary["messages_received"], 1)
        self.assertEqual(summary["duplicate_messages"], 1)
        self.assertEqual(summary["invalid_messages"], 1)

    # 12. Out-of-Order Sequence Handling
    def test_12_out_of_order_sequence_handling(self):
        validator = RealtimeDataValidator()
        t0 = datetime.now(timezone.utc)
        q1 = RealtimeQuote(
            symbol="NSE:RELIANCE",
            exchange="NSE",
            timestamp=t0,
            last_price=2800.0,
            volume=100.0,
            sequence_number=10,
        )
        q2 = RealtimeQuote(
            symbol="NSE:RELIANCE",
            exchange="NSE",
            timestamp=t0 + timedelta(seconds=1),
            last_price=2805.0,
            volume=150.0,
            sequence_number=5,  # Regression in sequence number
        )
        res1 = validator.validate(q1)
        self.assertTrue(res1.is_valid)
        res2 = validator.validate(q2)
        self.assertFalse(res2.is_valid)
        self.assertTrue(any("sequence" in err.lower() for err in res2.errors))

    # 13. Cache Updates
    def test_13_cache_updates(self):
        cache = LatestQuoteCache()
        t0 = datetime.now(timezone.utc)
        q = RealtimeQuote(
            symbol="NSE:RELIANCE",
            exchange="NSE",
            timestamp=t0,
            last_price=2900.0,
            volume=100.0,
        )
        updated = cache.update(q)
        self.assertTrue(updated)
        cached = cache.get_latest("RELIANCE")
        self.assertIsNotNone(cached)
        self.assertEqual(cached.last_price, 2900.0)

    # 14. Stale Cache Protection (No Backward Overwrite)
    def test_14_stale_cache_protection(self):
        cache = LatestQuoteCache()
        t1 = datetime.now(timezone.utc)
        t0 = t1 - timedelta(seconds=30)

        q_new = RealtimeQuote(
            symbol="NSE:TCS",
            exchange="NSE",
            timestamp=t1,
            last_price=3600.0,
            volume=500.0,
        )
        q_old = RealtimeQuote(
            symbol="NSE:TCS",
            exchange="NSE",
            timestamp=t0,
            last_price=3590.0,
            volume=400.0,
        )

        self.assertTrue(cache.update(q_new))
        # Attempt to overwrite with older quote
        rejected = cache.update(q_old)
        self.assertFalse(rejected)
        # Verify cached price is still 3600
        cached = cache.get_latest("NSE:TCS")
        self.assertEqual(cached.last_price, 3600.0)

    # 15. Disconnect Behavior
    def test_15_disconnect_behavior(self):
        provider = MockRealTimeProvider()
        provider.connect()
        self.assertTrue(provider.is_connected())
        provider.disconnect()
        self.assertFalse(provider.is_connected())
        self.assertEqual(provider.get_connection_state(), ConnectionState.DISCONNECTED)

    # 16. Bounded Reconnect with Exponential Backoff
    def test_16_bounded_reconnect_with_backoff(self):
        mgr = ConnectionManager(
            base_delay=0.01,
            max_delay=0.05,
            max_attempts=3,
        )
        self.assertEqual(mgr.state, ConnectionState.DISCONNECTED)
        self.assertTrue(mgr.can_retry())

        # Attempt 1
        d1 = mgr.compute_next_delay()
        mgr.increment_attempt()
        self.assertTrue(mgr.can_retry())

        # Attempt 2
        d2 = mgr.compute_next_delay()
        mgr.increment_attempt()
        self.assertTrue(mgr.can_retry())

        # Attempt 3 (reaches max_attempts=3)
        d3 = mgr.compute_next_delay()
        mgr.increment_attempt()
        self.assertFalse(mgr.can_retry())
        self.assertEqual(mgr.state, ConnectionState.FAILED)

        # Check delays are positive and strictly bounded by max_delay
        self.assertTrue(all(0.0 < d <= 0.05 for d in [d1, d2, d3]))

    # 17. Multi-Symbol Universe Subscription
    def test_17_multi_symbol_universe_subscription(self):
        provider = MockRealTimeProvider(seed=777)
        provider.connect()
        symbols = ["NSE:RELIANCE", "NSE:TCS", "NSE:INFY", "NSE:HDFCBANK", "NSE:ICICIBANK"]
        provider.subscribe(symbols)
        self.assertEqual(len(provider.get_subscribed_symbols()), 5)

        # Generate a tick for all
        quotes = [provider.generate_tick(s) for s in symbols]
        self.assertEqual(len(quotes), 5)
        for q in quotes:
            self.assertGreater(q.last_price, 0)
        provider.disconnect()

    # 18. Symbol Normalization
    def test_18_symbol_normalization(self):
        cases = [
            ("RELIANCE", "NSE:RELIANCE"),
            ("reliance", "NSE:RELIANCE"),
            ("RELIANCE.NS", "NSE:RELIANCE"),
            ("  INFY.ns  ", "NSE:INFY"),
            ("NSE:TCS", "NSE:TCS"),
            ("BSE:TCS", "BSE:TCS"),
            ("TCS.BO", "BSE:TCS"),
        ]
        for inp, expected in cases:
            norm = SymbolNormalizer.normalize(inp)
            self.assertEqual(norm.canonical, expected)

        # Invalid inputs
        for bad in ["", "   ", "::", "123::456:789"]:
            with self.assertRaises(ValueError):
                SymbolNormalizer.normalize(bad)

    # 19. Market Closed Session Handling
    def test_19_market_closed_session(self):
        monitor = FeedHealthMonitor()
        # Monday at 04:00 AM IST (before 09:00 AM)
        off_hours = datetime(2024, 4, 15, 4, 0, 0, tzinfo=IST_ZONE)
        session = monitor.get_market_session_state(off_hours)
        self.assertEqual(session, MarketSessionState.CLOSED)

    # 20. Market Holiday Session Handling
    def test_20_market_holiday_session(self):
        monitor = FeedHealthMonitor()
        # Republic Day 2024-01-26 (Friday) at 11:00 AM IST
        holiday_dt = datetime(2024, 1, 26, 11, 0, 0, tzinfo=IST_ZONE)
        session = monitor.get_market_session_state(holiday_dt)
        self.assertEqual(session, MarketSessionState.HOLIDAY)

        # Weekend Saturday
        weekend_dt = datetime(2024, 4, 13, 11, 0, 0, tzinfo=IST_ZONE)
        session_wknd = monitor.get_market_session_state(weekend_dt)
        self.assertEqual(session_wknd, MarketSessionState.WEEKEND)

    # 21. Historical -> Realtime Handoff
    def test_21_historical_realtime_handoff(self):
        handoff = HistoricalRealtimeHandoff(max_buffer_size=100)
        t0 = datetime(2024, 4, 1, 9, 15, tzinfo=IST_ZONE)

        hist_bars = [
            MarketBar(
                symbol="RELIANCE",
                exchange="NSE",
                timestamp=t0 + timedelta(minutes=5 * i),
                open=2800.0 + i,
                high=2810.0 + i,
                low=2795.0 + i,
                close=2805.0 + i,
                volume=10000.0,
            )
            for i in range(10)
        ]
        loaded = handoff.seed_history("NSE:RELIANCE", hist_bars)
        self.assertEqual(loaded, 10)
        self.assertEqual(handoff.get_bar_count("NSE:RELIANCE"), 10)

        # Real-time completed bar at next interval
        rt_bar = AggregatedBar(
            symbol="NSE:RELIANCE",
            start_time=t0 + timedelta(minutes=50),
            end_time=t0 + timedelta(minutes=55),
            open=2810.0,
            high=2820.0,
            low=2808.0,
            close=2818.0,
            volume=5000.0,
            is_complete=True,
        )
        ok = handoff.append_realtime_bar("NSE:RELIANCE", rt_bar)
        self.assertTrue(ok)
        self.assertEqual(handoff.get_bar_count("NSE:RELIANCE"), 11)

        df = handoff.get_combined_dataframe("NSE:RELIANCE")
        self.assertEqual(len(df), 11)
        self.assertEqual(df.iloc[-1]["close"], 2818.0)

    # 22. Bar Aggregation & Interval Alignment
    def test_22_bar_aggregation_alignment(self):
        agg = RealtimeBarAggregator(interval_seconds=300)  # 5 min
        t0 = datetime(2024, 4, 15, 9, 15, 10, tzinfo=IST_ZONE)

        # Tick 1 at 09:15:10
        q1 = RealtimeQuote(
            symbol="NSE:INFY",
            exchange="NSE",
            timestamp=t0,
            last_price=1500.0,
            volume=100.0,
        )
        agg.process_quote(q1)
        active = agg.get_active_bar("NSE:INFY")
        self.assertIsNotNone(active)
        self.assertEqual(active.open, 1500.0)
        self.assertEqual(active.high, 1500.0)
        self.assertEqual(active.low, 1500.0)
        self.assertEqual(active.close, 1500.0)
        self.assertFalse(active.is_complete)

        # Tick 2 at 09:16:30 (higher price, more volume)
        q2 = RealtimeQuote(
            symbol="NSE:INFY",
            exchange="NSE",
            timestamp=t0 + timedelta(seconds=80),
            last_price=1510.0,
            volume=250.0,
        )
        agg.process_quote(q2)
        active = agg.get_active_bar("NSE:INFY")
        self.assertEqual(active.high, 1510.0)
        self.assertEqual(active.close, 1510.0)
        self.assertEqual(active.volume, 250.0)

    # 23. Incomplete Bar Handling
    def test_23_incomplete_bar_handling(self):
        agg = RealtimeBarAggregator(interval_seconds=300)
        t0 = datetime(2024, 4, 15, 9, 15, 0, tzinfo=IST_ZONE)

        # Ticks within 09:15-09:20
        agg.process_quote(
            RealtimeQuote(symbol="NSE:TCS", exchange="NSE", timestamp=t0, last_price=3500.0, volume=100.0)
        )
        active = agg.get_active_bar("NSE:TCS")
        self.assertFalse(active.is_complete)

        # Next tick in the NEXT interval (09:20:05) completes previous bar
        t1 = datetime(2024, 4, 15, 9, 20, 5, tzinfo=IST_ZONE)
        completed = agg.process_quote(
            RealtimeQuote(symbol="NSE:TCS", exchange="NSE", timestamp=t1, last_price=3520.0, volume=200.0)
        )
        self.assertIsNotNone(completed)
        self.assertTrue(completed.is_complete)
        self.assertEqual(completed.close, 3500.0)

        completed_list = agg.get_completed_bars("NSE:TCS")
        self.assertEqual(len(completed_list), 1)

    # 24. Feature Warm-Up Buffer Verification
    def test_24_feature_warm_up_buffer(self):
        handoff = HistoricalRealtimeHandoff(max_buffer_size=300)
        t0 = datetime(2024, 1, 1, 9, 15, tzinfo=IST_ZONE)

        # Seed 150 bars (< 200 required)
        short_bars = [
            MarketBar(
                symbol="RELIANCE",
                exchange="NSE",
                timestamp=t0 + timedelta(days=i),
                open=2500.0 + i,
                high=2510.0 + i,
                low=2490.0 + i,
                close=2505.0 + i,
                volume=50000.0,
            )
            for i in range(150)
        ]
        handoff.seed_history("NSE:RELIANCE", short_bars)
        df_short = handoff.get_feature_ready_dataframe("NSE:RELIANCE", min_required_bars=200)
        self.assertEqual(len(df_short), 150)

        # Seed 250 bars (>= 200 required)
        long_bars = [
            MarketBar(
                symbol="RELIANCE",
                exchange="NSE",
                timestamp=t0 + timedelta(days=i),
                open=2500.0 + i,
                high=2510.0 + i,
                low=2490.0 + i,
                close=2505.0 + i,
                volume=50000.0,
            )
            for i in range(250)
        ]
        handoff.seed_history("NSE:RELIANCE", long_bars)
        df_long = handoff.get_feature_ready_dataframe("NSE:RELIANCE", min_required_bars=200)
        self.assertEqual(len(df_long), 250)
        self.assertGreaterEqual(len(df_long), 200)

    # 25. Downstream Paper-Only Safety Trace Test (Section 24)
    def test_25_downstream_paper_only_safety_trace(self):
        """
        Verify that real-time market data quotes CANNOT trigger real broker orders.
        Downstream execution must remain strictly isolated to paper trading.
        """
        from execution.adapters.kite_adapter import KiteBrokerAdapter
        from execution.exceptions import LiveTradingDisabledError
        from execution.models import PaperOrder, OrderSide, OrderType

        adapter = KiteBrokerAdapter(mock_mode=False)
        self.assertFalse(adapter.get_capabilities().supports_live_orders)

        order = PaperOrder(
            order_id="TEST_ORD_001",
            symbol="RELIANCE",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            requested_quantity=10,
        )
        with self.assertRaises(LiveTradingDisabledError):
            adapter.submit_order(order)
        with self.assertRaises(LiveTradingDisabledError):
            adapter.cancel_order("TEST_ORD_001")

        # RealTime provider itself has zero order placement capability
        provider = MockRealTimeProvider()
        self.assertFalse(hasattr(provider, "place_order"))
        self.assertFalse(hasattr(provider, "submit_order"))
        self.assertFalse(hasattr(provider, "cancel_order"))

    # 26. Dashboard Health Endpoint Verification
    def test_26_dashboard_endpoints(self):
        from dashboard.server import app
        client = app.test_client()

        # GET /api/realtime/health
        resp_health = client.get("/api/realtime/health")
        self.assertEqual(resp_health.status_code, 200)
        data_health = resp_health.get_json()
        self.assertIn("connection_state", data_health)
        self.assertIn("market_session", data_health)
        self.assertIn("overall_status", data_health)

        # GET /api/realtime/quotes
        resp_quotes = client.get("/api/realtime/quotes")
        self.assertEqual(resp_quotes.status_code, 200)
        data_quotes = resp_quotes.get_json()
        self.assertIn("quotes", data_quotes)
        self.assertIn("count", data_quotes)

    # 27. Credential Safety (No Secrets in Logs or Repr)
    def test_27_credential_safety(self):
        adapter = KiteRealTimeFeedAdapter(api_key="SECRET_KEY_123", access_token="SECRET_TOKEN_XYZ", mock_mode=True)
        rep = repr(adapter)
        s = str(adapter)
        self.assertNotIn("SECRET_KEY_123", rep)
        self.assertNotIn("SECRET_TOKEN_XYZ", rep)
        self.assertNotIn("SECRET_KEY_123", s)
        self.assertNotIn("SECRET_TOKEN_XYZ", s)

    # 28. Provider Failure Isolation
    def test_28_provider_failure_isolation(self):
        adapter = KiteRealTimeFeedAdapter(mock_mode=False)
        # In non-mock mode without valid connection, connect() must fail closed
        with self.assertRaises(MarketDataConnectionError):
            adapter.connect()
        self.assertEqual(adapter.get_connection_state(), ConnectionState.FAILED)

    # 29. Feed Health Metrics Accuracy
    def test_29_feed_health_metrics_accuracy(self):
        monitor = FeedHealthMonitor()
        for _ in range(10):
            monitor.record_message_received()
        for _ in range(8):
            monitor.record_message_valid()
        for _ in range(2):
            monitor.record_message_invalid()
        monitor.record_message_dropped()
        monitor.record_reconnect()

        summary = monitor.get_health_summary()
        self.assertEqual(summary["messages_received"], 10)
        self.assertEqual(summary["valid_messages"], 8)
        self.assertEqual(summary["invalid_messages"], 2)
        self.assertEqual(summary["dropped_messages"], 1)
        self.assertEqual(summary["reconnect_count"], 1)

    # 30. Bid/Ask Spread Validation
    def test_30_bid_ask_spread_validation(self):
        validator = RealtimeDataValidator()
        t0 = datetime.now(timezone.utc)

        # Crossed spread: bid > ask
        crossed_quote = RealtimeQuote(
            symbol="NSE:RELIANCE",
            exchange="NSE",
            timestamp=t0,
            last_price=2850.0,
            bid=2855.0,  # bid > ask
            ask=2850.0,
            volume=100.0,
        )
        res_crossed = validator.validate(crossed_quote)
        self.assertFalse(res_crossed.is_valid)
        self.assertTrue(any("crossed" in err.lower() for err in res_crossed.errors))

        # Normal valid spread: bid < ask
        valid_quote = RealtimeQuote(
            symbol="NSE:RELIANCE",
            exchange="NSE",
            timestamp=t0,
            last_price=2850.0,
            bid=2849.5,
            ask=2850.5,
            volume=100.0,
        )
        res_valid = validator.validate(valid_quote)
        self.assertTrue(res_valid.is_valid)


if __name__ == "__main__":
    unittest.main()
