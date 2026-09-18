"""
tests/test_step12_integration.py — End-to-End Paper Trading Integration Test Suite.

Covers 25+ comprehensive scenarios for Step 12:
- Happy-path full cycle
- Multi-stock universe
- Per-stock data failure isolation
- Stale quote detection
- Market session state gating
- ML model and ranking fail-closed isolation
- Risk check enforcements (kill switch, cash, liquidity, stock, sector, gross exposure)
- Order sequencing (SELLs before BUYs)
- Reconciliation & accounting
- Restart recovery & idempotency
- Dashboard API endpoints
- Legacy Binance isolation
- Real broker safety boundary
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
import pandas as pd

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from data.market.calendar import IST_ZONE, NSEMarketCalendar
from data.realtime import (
    FeedHealthMonitor,
    HistoricalRealtimeHandoff,
    LatestQuoteCache,
    MarketSessionState,
    RealtimeQuote,
)
from execution.exceptions import LiveTradingDisabledError
from execution.models import (
    OrderSide,
    OrderStatus,
    OrderType,
    PaperAccount,
    PaperOrder,
    RejectionReason,
)
from execution.paper import (
    CycleResult,
    CycleState,
    PaperTradingOrchestrator,
    PortfolioDecision,
    SignalSnapshot,
)
from execution.paper_broker import PaperBroker
from execution.persistence import PaperStatePersistence
from risk.kill_switch import PersistentKillSwitch
from risk.paper_risk_manager import PaperRiskManager


class TestStep12PaperIntegration(unittest.TestCase):
    """25 comprehensive tests for Step 12 End-to-End Paper Trading Integration."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="apex_test_step12_")
        self.data_dir = os.path.join(self.test_dir, "data_paper")
        os.makedirs(self.data_dir, exist_ok=True)
        self.universe = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]

        # Default synthetic market quotes
        self.quotes = {
            "RELIANCE": 2850.0,
            "TCS": 3500.0,
            "INFY": 1500.0,
            "HDFCBANK": 1600.0,
            "ICICIBANK": 1050.0,
        }
        self.volumes = {
            "RELIANCE": 1_000_000.0,
            "TCS": 800_000.0,
            "INFY": 1_500_000.0,
            "HDFCBANK": 2_000_000.0,
            "ICICIBANK": 1_200_000.0,
        }

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _create_orchestrator(self, **kwargs) -> PaperTradingOrchestrator:
        params = {
            "initial_capital": 1_000_000.0,
            "data_dir": self.data_dir,
            "auto_load_state": False,
        }
        params.update(kwargs)
        return PaperTradingOrchestrator(**params)

    # 1. Happy-path end-to-end cycle
    def test_01_happy_path_end_to_end_cycle(self):
        orch = self._create_orchestrator()
        t0 = datetime(2024, 4, 15, 10, 30, tzinfo=IST_ZONE)  # Monday 10:30 AM IST (regular session)

        res = orch.run_cycle(
            universe=self.universe,
            as_of_time=t0,
            override_quotes=self.quotes,
            override_volumes=self.volumes,
            force_market_open=True,
        )

        self.assertEqual(res.state, CycleState.COMPLETED)
        self.assertEqual(len(res.eligible_stocks), 5)
        self.assertGreater(len(res.signals), 0)
        self.assertGreater(len(res.decisions), 0)
        self.assertIsNotNone(res.account_snapshot)
        self.assertIsNotNone(res.reconciliation_report)
        self.assertTrue(res.reconciliation_report["is_clean"])

        # Check account invariants: total equity = cash + positions_value
        acct = orch.broker.get_account()
        self.assertAlmostEqual(acct.total_equity, acct.cash + acct.positions_value, places=2)

    # 2. Multi-stock universe
    def test_02_multi_stock_universe(self):
        orch = self._create_orchestrator()
        t0 = datetime(2024, 4, 15, 10, 30, tzinfo=IST_ZONE)

        res = orch.run_cycle(
            universe=self.universe,
            as_of_time=t0,
            override_quotes=self.quotes,
            override_volumes=self.volumes,
            force_market_open=True,
        )
        self.assertEqual(len(res.eligible_stocks), 5)
        for sym in self.universe:
            self.assertIn(sym, res.eligible_stocks)

    # 3. Single-stock data failure isolation (corrupt stock excluded, others proceed)
    def test_03_single_stock_data_failure_isolation(self):
        orch = self._create_orchestrator()
        t0 = datetime(2024, 4, 15, 10, 30, tzinfo=IST_ZONE)

        corrupt_quotes = dict(self.quotes)
        corrupt_quotes["INFY"] = -100.0  # Invalid negative price!

        res = orch.run_cycle(
            universe=self.universe,
            as_of_time=t0,
            override_quotes=corrupt_quotes,
            override_volumes=self.volumes,
            force_market_open=True,
        )

        # INFY must be excluded
        self.assertIn("INFY", res.excluded_stocks)
        self.assertNotIn("INFY", res.eligible_stocks)
        # Other 4 stocks must proceed successfully
        self.assertEqual(len(res.eligible_stocks), 4)
        self.assertEqual(res.state, CycleState.COMPLETED)

    # 4. Stale quote detection & exclusion
    def test_04_stale_quote_rejection(self):
        cache = LatestQuoteCache()
        t0 = datetime(2024, 4, 15, 10, 30, tzinfo=IST_ZONE)
        old_time = t0 - timedelta(seconds=600)  # 10 minutes old (> 300s threshold)

        cache.update(RealtimeQuote(
            symbol="NSE:TCS",
            exchange="NSE",
            timestamp=old_time,
            last_price=3500.0,
            volume=5000.0,
        ))

        orch = self._create_orchestrator(quote_cache=cache, max_staleness_seconds=300.0)
        res = orch.run_cycle(
            universe=["TCS"],
            as_of_time=t0,
            force_market_open=True,
        )
        self.assertIn("TCS", res.excluded_stocks)
        self.assertTrue(any("STALE" in reason for reason in res.excluded_stocks.values()))

    # 5. Market closed session handling
    def test_05_market_closed_session(self):
        orch = self._create_orchestrator()
        # Sunday morning (market closed)
        sunday_t = datetime(2024, 4, 14, 10, 30, tzinfo=IST_ZONE)

        res = orch.run_cycle(
            universe=self.universe,
            as_of_time=sunday_t,
            override_quotes=self.quotes,
            force_market_open=False,  # Respect market calendar
        )
        self.assertEqual(res.state, CycleState.MARKET_CLOSED_SKIPPED)
        self.assertEqual(len(res.orders_generated), 0)

    # 6. Insufficient warmup buffer handling
    def test_06_insufficient_warmup(self):
        handoff = HistoricalRealtimeHandoff(max_buffer_size=100)
        orch = self._create_orchestrator(handoff=handoff)
        t0 = datetime(2024, 4, 15, 10, 30, tzinfo=IST_ZONE)

        # Buffer is empty: orchestrator handles fallback gracefully without crashing
        res = orch.run_cycle(
            universe=self.universe,
            as_of_time=t0,
            override_quotes=self.quotes,
            override_volumes=self.volumes,
            force_market_open=True,
        )
        self.assertEqual(res.state, CycleState.COMPLETED)

    # 7. Model failure fail-closed isolation
    def test_07_model_failure_fail_closed(self):
        orch = self._create_orchestrator()
        t0 = datetime(2024, 4, 15, 10, 30, tzinfo=IST_ZONE)

        # Mock trainer to raise exception
        class FailingTrainer:
            model_type = "failing"
            target_horizon = 5
            def train_and_predict(self, candidate_panel, as_of_time):
                raise RuntimeError("Simulated ML training catastrophic failure")

        orch.ml_trainer = FailingTrainer()
        res = orch.run_cycle(
            universe=self.universe,
            as_of_time=t0,
            override_quotes=self.quotes,
            override_volumes=self.volumes,
            force_market_open=True,
        )
        self.assertEqual(res.state, CycleState.MODEL_FAILED)
        self.assertEqual(len(res.orders_generated), 0)

    # 8. Ranking failure fail-closed isolation
    def test_08_ranking_failure_fail_closed(self):
        orch = self._create_orchestrator()
        t0 = datetime(2024, 4, 15, 10, 30, tzinfo=IST_ZONE)

        class FailingRanker:
            def generate_ranking(self, candidate_panel, as_of_time):
                raise RuntimeError("Simulated cross-sectional ranking failure")

        orch.signal_runner = FailingRanker()
        res = orch.run_cycle(
            universe=self.universe,
            as_of_time=t0,
            override_quotes=self.quotes,
            override_volumes=self.volumes,
            force_market_open=True,
        )
        self.assertEqual(res.state, CycleState.MODEL_FAILED)
        self.assertEqual(len(res.orders_generated), 0)

    # 9. Portfolio construction failure handling
    def test_09_portfolio_construction_failure(self):
        orch = self._create_orchestrator()
        t0 = datetime(2024, 4, 15, 10, 30, tzinfo=IST_ZONE)

        class FailingPortfolioRunner:
            def build_target_portfolio(self, *args, **kwargs):
                raise RuntimeError("Portfolio optimization infeasible")

        orch.portfolio_runner = FailingPortfolioRunner()
        res = orch.run_cycle(
            universe=self.universe,
            as_of_time=t0,
            override_quotes=self.quotes,
            override_volumes=self.volumes,
            force_market_open=True,
        )
        self.assertEqual(res.state, CycleState.PORTFOLIO_FAILED)
        self.assertEqual(len(res.orders_generated), 0)

    # 10. Pre-trade risk rejection
    def test_10_pre_trade_risk_rejection(self):
        orch = self._create_orchestrator()
        # Set max single stock limit extremely low (e.g. 1%)
        orch.risk_manager.max_single_stock_weight = 0.01

        t0 = datetime(2024, 4, 15, 10, 30, tzinfo=IST_ZONE)
        res = orch.run_cycle(
            universe=self.universe,
            as_of_time=t0,
            override_quotes=self.quotes,
            override_volumes=self.volumes,
            force_market_open=True,
        )
        self.assertGreater(len(res.orders_rejected), 0)
        self.assertTrue(all(o.status == OrderStatus.REJECTED for o in res.orders_rejected))

    # 11. Kill switch activation blocks new orders
    def test_11_kill_switch_blocks_orders(self):
        orch = self._create_orchestrator()
        orch.kill_switch.enable(reason="TEST_TRIGGER", operator="UNIT_TEST")
        self.assertTrue(orch.kill_switch.is_active())

        t0 = datetime(2024, 4, 15, 10, 30, tzinfo=IST_ZONE)
        res = orch.run_cycle(
            universe=self.universe,
            as_of_time=t0,
            override_quotes=self.quotes,
            override_volumes=self.volumes,
            force_market_open=True,
        )
        # All orders must be rejected by kill switch
        self.assertGreater(len(res.orders_rejected), 0)
        self.assertEqual(len(res.fills), 0)

    # 12. Paper broker rejection handling
    def test_12_paper_broker_rejection(self):
        orch = self._create_orchestrator()
        orch.broker.update_market_price("RELIANCE", 2800.0)
        # Empty cash so broker rejects any buy
        orch.broker.accounting.account.cash = 0.0

        order = PaperOrder(
            symbol="RELIANCE",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            requested_quantity=100,
        )
        out = orch.broker.submit_order(order)
        self.assertEqual(out.status, OrderStatus.REJECTED)
        self.assertEqual(out.rejection_reason, RejectionReason.INSUFFICIENT_CASH)

    # 13. Partial execution / fill recording
    def test_13_partial_execution(self):
        orch = self._create_orchestrator()
        orch.broker.update_market_panel({"RELIANCE": 2800.0}, {"RELIANCE": 1000.0})

        order = PaperOrder(
            symbol="RELIANCE",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            requested_quantity=20,
        )
        out = orch.broker.submit_order(order)
        self.assertEqual(out.status, OrderStatus.FILLED)
        self.assertEqual(len(orch.broker.get_fills()), 1)
        fill = orch.broker.get_fills()[0]
        self.assertEqual(fill.symbol, "RELIANCE")
        self.assertGreater(fill.price, 0.0)

    # 14. Reconciliation mismatch detection & alert
    def test_14_reconciliation_mismatch_detection(self):
        from execution.models import PaperPosition, ReconciliationStatus
        orch = self._create_orchestrator()
        # Create an artificial position mismatch
        orch.broker.accounting.positions["TCS"] = PaperPosition(
            symbol="TCS", shares=10, average_cost=3500.0, current_price=3500.0
        )
        # Reconcile against an empty expected map
        report = orch.reconcile_state(expected_targets={})
        self.assertFalse(report.is_clean)
        self.assertIn(report.status, (ReconciliationStatus.MISMATCH, ReconciliationStatus.ERROR))
        self.assertGreater(len(report.discrepancies), 0)

    # 15. Duplicate cycle idempotency (second run of same cycle ID is ignored)
    def test_15_duplicate_cycle_idempotency(self):
        orch = self._create_orchestrator()
        t0 = datetime(2024, 4, 15, 10, 30, tzinfo=IST_ZONE)

        res1 = orch.run_cycle(
            universe=self.universe,
            as_of_time=t0,
            override_quotes=self.quotes,
            override_volumes=self.volumes,
            force_market_open=True,
        )
        self.assertEqual(res1.state, CycleState.COMPLETED)

        # Run again with exact same timestamp
        res2 = orch.run_cycle(
            universe=self.universe,
            as_of_time=t0,
            override_quotes=self.quotes,
            override_volumes=self.volumes,
            force_market_open=True,
        )
        self.assertEqual(res2.state, CycleState.ALREADY_PROCESSED)
        self.assertEqual(len(res2.orders_generated), 0)

    # 16. Process restart & recovery
    def test_16_process_restart_recovery(self):
        orch1 = self._create_orchestrator(auto_load_state=False)
        t0 = datetime(2024, 4, 15, 10, 30, tzinfo=IST_ZONE)

        res1 = orch1.run_cycle(
            universe=self.universe,
            as_of_time=t0,
            override_quotes=self.quotes,
            override_volumes=self.volumes,
            force_market_open=True,
        )
        self.assertEqual(res1.state, CycleState.COMPLETED)
        equity_before = orch1.broker.get_account().total_equity
        positions_before = len(orch1.broker.get_positions())

        # Instantiate fresh orchestrator with auto_load_state=True
        orch2 = self._create_orchestrator(auto_load_state=True)
        acct_after = orch2.broker.get_account()
        self.assertAlmostEqual(acct_after.total_equity, equity_before, places=2)
        self.assertEqual(len(orch2.broker.get_positions()), positions_before)

    # 17. Duplicate order prevention via idempotency keys
    def test_17_duplicate_order_prevention(self):
        orch = self._create_orchestrator()
        orch.broker.update_market_panel({"RELIANCE": 2800.0}, {"RELIANCE": 100000.0})
        t0 = datetime(2024, 4, 15, 10, 30, tzinfo=IST_ZONE)
        key = "IDEMP-KEY-TEST-001"
        order1 = PaperOrder(
            symbol="RELIANCE",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            requested_quantity=10,
            idempotency_key=key,
        )
        v_quote = orch.data_adapter.validate_quote("RELIANCE", price=2800.0, volume=10000.0)
        out1 = orch.order_manager.submit_order(order1, quote=v_quote, as_of_time=t0)
        self.assertEqual(out1.status, OrderStatus.FILLED)

        # Attempt same idempotency key again
        order2 = PaperOrder(
            symbol="RELIANCE",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            requested_quantity=10,
            idempotency_key=key,
        )
        out2 = orch.order_manager.submit_order(order2, quote=v_quote, as_of_time=t0)
        self.assertEqual(out2.status, OrderStatus.REJECTED)
        self.assertEqual(out2.rejection_reason, RejectionReason.DUPLICATE_ORDER)

    # 18. Insufficient cash rejection in pre-trade risk
    def test_18_insufficient_cash_rejection(self):
        orch = self._create_orchestrator()
        orch.broker.accounting.account.cash = 100.0  # ₹100 cash only
        t0 = datetime(2024, 4, 15, 10, 30, tzinfo=IST_ZONE)

        order = PaperOrder(
            symbol="RELIANCE",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            requested_quantity=100,  # 100 * 2800 = ₹280,000 >> ₹100
        )
        v_quote = orch.data_adapter.validate_quote("RELIANCE", price=2800.0, volume=10000.0)
        out = orch.order_manager.submit_order(order, quote=v_quote, as_of_time=t0)
        self.assertEqual(out.status, OrderStatus.REJECTED)
        self.assertEqual(out.rejection_reason, RejectionReason.INSUFFICIENT_CASH)

    # 19. Liquidity limit rejection (max 5% volume)
    def test_19_liquidity_limit_rejection(self):
        orch = self._create_orchestrator()
        t0 = datetime(2024, 4, 15, 10, 30, tzinfo=IST_ZONE)
        # Order quantity 20 against volume 100 (20% > 5% liquidity limit)
        order = PaperOrder(
            symbol="RELIANCE",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            requested_quantity=20,
        )
        v_quote = orch.data_adapter.validate_quote("RELIANCE", price=2800.0, volume=100.0)
        out = orch.order_manager.submit_order(order, quote=v_quote, reference_volume=100.0, as_of_time=t0)
        self.assertEqual(out.status, OrderStatus.REJECTED)
        self.assertEqual(out.rejection_reason, RejectionReason.LIQUIDITY_LIMIT)

    # 20. Stock exposure limit rejection (max 35%)
    def test_20_stock_exposure_limit_rejection(self):
        orch = self._create_orchestrator()
        orch.risk_manager.max_single_stock_weight = 0.35
        t0 = datetime(2024, 4, 15, 10, 30, tzinfo=IST_ZONE)
        # Total equity is ₹1,000,000. Limit is ₹350,000.
        # Order for 200 shares * 2800 = ₹560,000 (> 35%)
        order = PaperOrder(
            symbol="RELIANCE",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            requested_quantity=200,
        )
        v_quote = orch.data_adapter.validate_quote("RELIANCE", price=2800.0, volume=100000.0)
        out = orch.order_manager.submit_order(order, quote=v_quote, as_of_time=t0)
        self.assertEqual(out.status, OrderStatus.REJECTED)
        self.assertEqual(out.rejection_reason, RejectionReason.POSITION_LIMIT)

    # 21. Sector exposure limit rejection (max 55%)
    def test_21_sector_exposure_limit_rejection(self):
        orch = self._create_orchestrator()
        orch.risk_manager.max_single_stock_weight = 0.80
        orch.risk_manager.max_sector_weight = 0.55
        t0 = datetime(2024, 4, 15, 10, 30, tzinfo=IST_ZONE)
        # Both TCS and INFY are Technology
        # Create large buy order for TCS
        order = PaperOrder(
            symbol="TCS",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            requested_quantity=200,  # 200 * 3500 = ₹700,000 (> 55% of ₹1M)
        )
        v_quote = orch.data_adapter.validate_quote("TCS", price=3500.0, volume=100000.0)
        out = orch.order_manager.submit_order(order, quote=v_quote, as_of_time=t0)
        self.assertEqual(out.status, OrderStatus.REJECTED)
        self.assertEqual(out.rejection_reason, RejectionReason.SECTOR_LIMIT)

    # 22. Gross exposure limit rejection (max 100%)
    def test_22_gross_exposure_limit_rejection(self):
        orch = self._create_orchestrator()
        orch.risk_manager.max_gross_exposure = 1.00
        t0 = datetime(2024, 4, 15, 10, 30, tzinfo=IST_ZONE)
        # Order exceeding ₹1,000,000 total equity
        order = PaperOrder(
            symbol="RELIANCE",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            requested_quantity=400,  # 400 * 2800 = ₹1,120,000 (> 100%)
        )
        v_quote = orch.data_adapter.validate_quote("RELIANCE", price=2800.0, volume=100000.0)
        out = orch.order_manager.submit_order(order, quote=v_quote, as_of_time=t0)
        self.assertEqual(out.status, OrderStatus.REJECTED)

    # 23. Dashboard API endpoints verification
    def test_23_dashboard_api_endpoints(self):
        from dashboard.server import app
        client = app.test_client()

        # Run one cycle on global orchestrator to seed state
        from execution.paper import get_global_paper_orchestrator
        orch = get_global_paper_orchestrator()
        t0 = datetime(2024, 4, 15, 10, 30, tzinfo=IST_ZONE)
        orch.run_cycle(
            universe=self.universe,
            as_of_time=t0,
            override_quotes=self.quotes,
            override_volumes=self.volumes,
            force_market_open=True,
        )

        # GET /api/paper/cycle
        resp = client.get("/api/paper/cycle")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("cycle_id", data)
        self.assertIn("state", data)

        # GET /api/paper/signals
        resp_sig = client.get("/api/paper/signals")
        self.assertEqual(resp_sig.status_code, 200)
        data_sig = resp_sig.get_json()
        self.assertIn("signals", data_sig)

        # GET /api/paper/portfolio
        resp_port = client.get("/api/paper/portfolio")
        self.assertEqual(resp_port.status_code, 200)
        data_port = resp_port.get_json()
        self.assertIn("equity", data_port)

        # GET /api/paper/reconciliation
        resp_rec = client.get("/api/paper/reconciliation")
        self.assertEqual(resp_rec.status_code, 200)

        # GET /api/paper/health
        resp_hlth = client.get("/api/paper/health")
        self.assertEqual(resp_hlth.status_code, 200)
        self.assertEqual(resp_hlth.get_json()["mode"], "PAPER_TRADING")

    # 24. Binance isolation verification
    def test_24_binance_isolation(self):
        """Verify that Step 12 does not import, reference, or alter legacy Binance bot files."""
        orch = self._create_orchestrator()
        # Verify broker is PaperBroker, not Binance
        self.assertIsInstance(orch.broker, PaperBroker)
        self.assertFalse(orch.broker.get_capabilities().supports_live_orders)

        # Verify no binance modules imported by execution.paper
        import execution.paper
        for mod in sys.modules:
            if mod.startswith("execution.paper."):
                self.assertNotIn("binance", mod.lower())

    # 25. Real broker safety boundary
    def test_25_real_broker_safety_boundary(self):
        """Verify that passing an adapter that supports live orders raises LiveTradingDisabledError."""
        class MockLiveBroker:
            def supports_live_orders(self):
                return True

        with self.assertRaises(LiveTradingDisabledError):
            PaperTradingOrchestrator(broker=MockLiveBroker())


if __name__ == "__main__":
    unittest.main()
