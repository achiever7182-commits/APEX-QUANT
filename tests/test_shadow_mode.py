"""
tests/test_shadow_mode.py — Focused tests for True Shadow Mode pipeline.

Covers:
1. Feed connection success using a mocked Kite provider
2. Missing credentials (fails closed)
3. Invalid credentials (fails closed)
4. Feed disconnect handling
5. Feed reconnect handling
6. Live feed data reaches orchestrator
7. Synthetic fallback is impossible in REAL SHADOW MODE
8. Shadow order is simulated
9. No broker order is sent
10. Stale data fails safely
11. Malformed tick fails safely
12. End-to-end shadow pipeline using a controlled mocked live-feed stream
"""

import os
import sys
import time
from datetime import datetime, timezone, timedelta
import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from data.realtime.models import ConnectionState, RealtimeQuote
from data.realtime.kite_feed import KiteRealTimeFeedAdapter
from execution.paper.orchestrator import PaperTradingOrchestrator
from execution.paper.models import CycleState
from execution.exceptions import LiveTradingDisabledError
from data.realtime import get_global_quote_cache


class TestShadowMode(unittest.TestCase):
    
    def setUp(self):
        # Clear environment variables to start clean
        if "KITE_API_KEY" in os.environ:
            del os.environ["KITE_API_KEY"]
        if "KITE_ACCESS_TOKEN" in os.environ:
            del os.environ["KITE_ACCESS_TOKEN"]
            
        self.cache = get_global_quote_cache()
        self.cache.clear()

    # 1. feed connection success using a mocked Kite provider (MOCKED FEED TESTS)
    @patch("data.realtime.kite_feed.KiteTicker")
    def test_01_feed_connection_success_mocked(self, mock_ticker_class):
        mock_instance = MagicMock()
        mock_ticker_class.return_value = mock_instance
        
        feed = KiteRealTimeFeedAdapter(api_key="TEST_API", access_token="TEST_TOKEN")
        res = feed.connect()
        
        self.assertTrue(res)
        self.assertEqual(feed.get_connection_state(), ConnectionState.CONNECTING)
        
        # Simulate websocket connected callback
        feed._on_connect(None, None)
        self.assertEqual(feed.get_connection_state(), ConnectionState.CONNECTED)
        self.assertTrue(feed.is_connected())

    # 2. missing credentials
    def test_02_missing_credentials_fails_closed(self):
        # Explicitly no env vars set
        feed = KiteRealTimeFeedAdapter()
        res = feed.connect()
        
        self.assertFalse(res)
        self.assertFalse(feed.is_connected())
        self.assertEqual(feed.get_connection_state(), ConnectionState.FAILED)

    # 3. invalid credentials
    @patch("data.realtime.kite_feed.KiteTicker")
    def test_03_invalid_credentials(self, mock_ticker_class):
        # Simulate kite connect throwing an auth exception on connect
        mock_ticker_class.side_effect = Exception("Invalid credentials")
        
        feed = KiteRealTimeFeedAdapter(api_key="BAD", access_token="BAD")
        res = feed.connect()
        
        self.assertFalse(res)
        self.assertFalse(feed.is_connected())
        self.assertEqual(feed.get_connection_state(), ConnectionState.FAILED)

    # 4. feed disconnect
    @patch("data.realtime.kite_feed.KiteTicker")
    def test_04_feed_disconnect(self, mock_ticker_class):
        feed = KiteRealTimeFeedAdapter(api_key="TEST", access_token="TEST")
        feed.connect()
        feed._on_connect(None, None)
        self.assertTrue(feed.is_connected())
        
        # Simulate close callback
        feed._on_close(None, 1000, "Closed")
        self.assertFalse(feed.is_connected())
        self.assertEqual(feed.get_connection_state(), ConnectionState.DISCONNECTED)

    # 5. feed reconnect
    @patch("data.realtime.kite_feed.KiteTicker")
    def test_05_feed_reconnect(self, mock_ticker_class):
        feed = KiteRealTimeFeedAdapter(api_key="TEST", access_token="TEST")
        feed.connect()
        feed._on_reconnect(None, 2)
        
        self.assertFalse(feed.is_connected())
        self.assertEqual(feed.get_connection_state(), ConnectionState.RECONNECTING)
        self.assertEqual(feed._reconnect_attempts, 2)

    # 6. live feed data reaches orchestrator
    @patch("data.realtime.kite_feed.KiteTicker")
    def test_06_live_feed_data_reaches_orchestrator(self, mock_ticker_class):
        feed = KiteRealTimeFeedAdapter(api_key="TEST", access_token="TEST")
        feed.register_callback(self.cache.update)
        feed.connect()
        feed._on_connect(None, None)
        feed.subscribe(["TCS"])
        
        # Simulate incoming tick
        now = datetime.now(timezone.utc)
        tick = {
            "instrument_token": feed._symbol_to_token.get("NSE:TCS"),
            "last_price": 3600.0,
            "volume_traded": 150000,
            "exchange_timestamp": now,
        }
        feed._on_ticks(None, [tick])
        
        # Verify cache has data
        cached_quote = self.cache.get_latest("TCS")
        self.assertIsNotNone(cached_quote)
        self.assertEqual(cached_quote.last_price, 3600.0)

    # 7. synthetic fallback is impossible in REAL SHADOW MODE
    def test_07_synthetic_fallback_disabled(self):
        orch = PaperTradingOrchestrator()
        
        # Provide override quotes so it passes Step 2 (Data Validation) and hits Step 3 (Feature Generation)
        with self.assertRaisesRegex(RuntimeError, "Synthetic fallback is disabled"):
            orch.run_cycle(
                universe=["RELIANCE"],
                override_quotes={"RELIANCE": 2000.0},
                disable_synthetic_fallback=True,  # STRICT MODE
                force_market_open=True
            )

    # 8. shadow order is simulated & 9. no broker order is sent
    def test_08_09_shadow_orders_simulated_only(self):
        orch = PaperTradingOrchestrator()
        self.assertFalse(orch.broker.get_capabilities().supports_live_orders)
        
        # Attempt to inject live broker
        class LiveBrokerMock:
            def supports_live_orders(self): return True
            
        with self.assertRaises(LiveTradingDisabledError):
            PaperTradingOrchestrator(broker=LiveBrokerMock())

    # 10. stale data fails safely
    @patch("data.realtime.kite_feed.KiteTicker")
    def test_10_stale_data_fails_safely(self, mock_ticker_class):
        feed = KiteRealTimeFeedAdapter(api_key="TEST", access_token="TEST")
        feed.register_callback(self.cache.update)
        feed.connect()
        feed._on_connect(None, None)
        feed.subscribe(["RELIANCE"])
        
        # Simulate extremely stale tick
        stale_time = datetime.now(timezone.utc) - timedelta(minutes=10)
        tick = {
            "instrument_token": feed._symbol_to_token.get("NSE:RELIANCE"),
            "last_price": 2800.0,
            "volume_traded": 100,
            "exchange_timestamp": stale_time,
        }
        feed._on_ticks(None, [tick])
        
        orch = PaperTradingOrchestrator(max_staleness_seconds=300)
        cycle = orch.run_cycle(
            universe=["RELIANCE"],
            disable_synthetic_fallback=True,
            force_market_open=True,
            as_of_time=datetime.now(timezone.utc)
        )
        
        self.assertEqual(cycle.state, CycleState.DATA_FAILED)
        self.assertIn("RELIANCE", cycle.excluded_stocks)
        self.assertTrue(any("STALE" in reason for reason in cycle.excluded_stocks.values()))

    # 11. malformed tick fails safely
    @patch("data.realtime.kite_feed.KiteTicker")
    def test_11_malformed_tick_fails_safely(self, mock_ticker_class):
        feed = KiteRealTimeFeedAdapter(api_key="TEST", access_token="TEST")
        feed.register_callback(self.cache.update)
        feed.connect()
        feed._on_connect(None, None)
        feed.subscribe(["INFY"])
        
        # Simulate tick with crossed spreads and negative price
        tick = {
            "instrument_token": feed._symbol_to_token.get("NSE:INFY"),
            "last_price": -50.0, # INVALID
            "exchange_timestamp": datetime.now(timezone.utc),
        }
        
        errors_before = feed._errors_count
        feed._on_ticks(None, [tick])
        
        # Tick is rejected silently by feed layer or generates no valid quote
        cached = self.cache.get_latest("INFY")
        self.assertIsNone(cached)
        
        orch = PaperTradingOrchestrator()
        cycle = orch.run_cycle(
            universe=["INFY"],
            disable_synthetic_fallback=True,
            force_market_open=True
        )
        self.assertEqual(cycle.state, CycleState.DATA_FAILED)
        self.assertIn("INFY", cycle.excluded_stocks)

    # 12. end-to-end shadow pipeline using a controlled mocked live-feed stream
    @patch("data.realtime.kite_feed.KiteTicker")
    def test_12_end_to_end_mocked_live_feed(self, mock_ticker_class):
        feed = KiteRealTimeFeedAdapter(api_key="TEST", access_token="TEST")
        feed.register_callback(self.cache.update)
        feed.connect()
        feed._on_connect(None, None)
        feed.subscribe(["HDFCBANK"])
        
        now = datetime.now(timezone.utc)
        tick = {
            "instrument_token": feed._symbol_to_token.get("NSE:HDFCBANK"),
            "last_price": 1600.0,
            "volume_traded": 500000,
            "exchange_timestamp": now,
        }
        feed._on_ticks(None, [tick])
        
        orch = PaperTradingOrchestrator()
        
        # Also need a history bar to allow portfolio construction
        hist_bars = {
            "NSE:HDFCBANK": pd.DataFrame([{
                "timestamp": now,
                "symbol": "NSE:HDFCBANK",
                "open": 1600.0,
                "high": 1600.0,
                "low": 1600.0,
                "close": 1600.0,
                "volume": 500000
            }])
        }
        
        # Override candidate_panel to skip step 3 entirely and reach step 6
        candidate_panel = pd.DataFrame([{
            "timestamp": now,
            "symbol": "HDFCBANK",
            "close": 1600.0,
            "volume": 500000,
            "turnover": 800000000,
            "sector": "Financials",
            "predicted_return": 0.05,
        }])
        
        # Override the history in the orchestrator by passing it directly
        cycle = orch.run_cycle(
            universe=["HDFCBANK"],
            candidate_panel=candidate_panel,
            disable_synthetic_fallback=True,
            force_market_open=True,
            as_of_time=now,
            market_bars_history=hist_bars
        )
        
        self.assertIn(cycle.state, [CycleState.COMPLETED, CycleState.RECONCILIATION_FAILED])
        self.assertIn("HDFCBANK", cycle.eligible_stocks)
        self.assertTrue(len(cycle.decisions) > 0)


if __name__ == "__main__":
    unittest.main()
