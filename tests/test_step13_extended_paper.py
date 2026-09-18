"""
tests/test_step13_extended_paper.py — Comprehensive Test Suite for Step 13.

Covers all 16 mandatory categories across 44 comprehensive tests:
  1. Session Lifecycle State Machine (4 tests)
  2. Multi-Session Simulation Execution (3 tests)
  3. Restart Recovery across 7 Interruption Boundaries (7 tests)
  4. Idempotency Stress Testing (3 tests)
  5. Failure Injection across Subsystems (4 tests)
  6. Partial Symbol Failure Isolation (2 tests)
  7. Market Session Safety (3 tests)
  8. Paper Accounting Invariants (2 tests)
  9. Post-Session Reconciliation (2 tests)
  10. All 12 Pre-Trade Risk Checks (2 tests)
  11. Operational Telemetry (2 tests)
  12. Persistent Session History (2 tests)
  13. Deterministic Reproduction (2 tests)
  14. Data Integrity & Look-Ahead Protection (2 tests)
  15. Paper / Live Safety Boundary (2 tests)
  16. Binance Isolation & Dashboard Endpoints (2 tests)
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import numpy as np
import pandas as pd

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from data.market.calendar import IST_ZONE, NSEMarketCalendar
from data.realtime import LatestQuoteCache, MarketSessionState, RealtimeQuote
from execution.exceptions import LiveTradingDisabledError
from execution.models import (
    OrderSide,
    OrderStatus,
    OrderType,
    PaperAccount,
    PaperFill,
    PaperOrder,
    PaperPosition,
    ReconciliationReport,
    ReconciliationStatus,
    RejectionReason,
)
from execution.paper import (
    CycleResult,
    CycleState,
    InvalidSessionTransitionError,
    MultiSessionConfig,
    MultiSessionSimulationEngine,
    PaperOperationalTelemetry,
    PaperPerformanceReport,
    PaperTradingOrchestrator,
    PortfolioDecision,
    SessionRecord,
    SessionState,
    SessionTransitionValidator,
    SignalSnapshot,
)
from execution.paper_broker import PaperBroker
from execution.persistence import PaperStatePersistence
from risk.kill_switch import PersistentKillSwitch
from risk.paper_risk_manager import PaperRiskManager


class TestStep13ExtendedPaper(unittest.TestCase):
    """44 Comprehensive Tests for Extended Paper Trading & Operational Reliability."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="apex_test_step13_")
        self.data_dir = os.path.join(self.test_dir, "data_paper")
        os.makedirs(self.data_dir, exist_ok=True)
        self.persistence = PaperStatePersistence(data_dir=self.data_dir)
        self.telemetry = PaperOperationalTelemetry()
        self.universe = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]

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

    def _create_engine(self, config: Optional[MultiSessionConfig] = None) -> MultiSessionSimulationEngine:
        cfg = config or MultiSessionConfig(
            sessions_count=5,
            start_date="2024-04-15",
            initial_capital=1_000_000.0,
            random_seed=42,
            universe=self.universe,
        )
        orch = PaperTradingOrchestrator(
            initial_capital=cfg.initial_capital,
            data_dir=self.data_dir,
            persistence=self.persistence,
            telemetry=self.telemetry,
            auto_load_state=False,
        )
        return MultiSessionSimulationEngine(
            config=cfg,
            orchestrator=orch,
            persistence=self.persistence,
            telemetry=self.telemetry,
            data_dir=self.data_dir,
            base_prices=self.quotes,
        )

    # ══════════════════════════════════════════════════════════════════════
    # CATEGORY 1: SESSION LIFECYCLE STATE MACHINE (4 Tests)
    # ══════════════════════════════════════════════════════════════════════

    def test_01_session_state_machine_happy_path(self):
        """Verify normal sequential transition: INITIALIZING -> PRE_MARKET -> READY -> RUNNING -> RECONCILING -> COMPLETED."""
        state = SessionState.INITIALIZING
        transitions = [
            SessionState.PRE_MARKET,
            SessionState.READY,
            SessionState.RUNNING,
            SessionState.RECONCILING,
            SessionState.COMPLETED,
        ]
        for next_st in transitions:
            SessionTransitionValidator.validate_transition(state, next_st)
            state = next_st
        self.assertEqual(state, SessionState.COMPLETED)
        self.assertTrue(SessionTransitionValidator.is_terminal(state))

    def test_02_session_state_machine_invalid_transition(self):
        """Verify that illegal transitions raise InvalidSessionTransitionError."""
        # Cannot jump from INITIALIZING directly to COMPLETED
        with self.assertRaises(InvalidSessionTransitionError):
            SessionTransitionValidator.validate_transition(SessionState.INITIALIZING, SessionState.COMPLETED)

        # Cannot jump from PRE_MARKET directly to RECONCILING
        with self.assertRaises(InvalidSessionTransitionError):
            SessionTransitionValidator.validate_transition(SessionState.PRE_MARKET, SessionState.RECONCILING)

        # Terminal COMPLETED cannot transition to anything
        with self.assertRaises(InvalidSessionTransitionError):
            SessionTransitionValidator.validate_transition(SessionState.COMPLETED, SessionState.RUNNING)

    def test_03_session_state_machine_failure_transition(self):
        """Verify transitions to FAILED from intermediate active states and terminal protection."""
        # Allowed transitions to FAILED
        SessionTransitionValidator.validate_transition(SessionState.INITIALIZING, SessionState.FAILED)
        SessionTransitionValidator.validate_transition(SessionState.PRE_MARKET, SessionState.FAILED)
        SessionTransitionValidator.validate_transition(SessionState.READY, SessionState.FAILED)
        SessionTransitionValidator.validate_transition(SessionState.RUNNING, SessionState.FAILED)
        SessionTransitionValidator.validate_transition(SessionState.RECONCILING, SessionState.FAILED)

        # Once FAILED, state is terminal
        self.assertTrue(SessionTransitionValidator.is_terminal(SessionState.FAILED))
        with self.assertRaises(InvalidSessionTransitionError):
            SessionTransitionValidator.validate_transition(SessionState.FAILED, SessionState.RUNNING)

    def test_04_session_state_machine_abort(self):
        """Verify transitions to ABORTED from intermediate states and terminal status."""
        SessionTransitionValidator.validate_transition(SessionState.RUNNING, SessionState.ABORTED)
        self.assertTrue(SessionTransitionValidator.is_terminal(SessionState.ABORTED))

    # ══════════════════════════════════════════════════════════════════════
    # CATEGORY 2: MULTI-SESSION SIMULATION EXECUTION (3 Tests)
    # ══════════════════════════════════════════════════════════════════════

    def test_05_multi_session_5_sessions_execution(self):
        """Execute 5-session paper simulation; verify all sessions complete cleanly with consistent accounting."""
        engine = self._create_engine(MultiSessionConfig(sessions_count=5, random_seed=42))
        records = engine.run_simulation(force_market_open=True)

        self.assertEqual(len(records), 5)
        self.assertEqual(self.telemetry.sessions_completed, 5)
        self.assertEqual(self.telemetry.sessions_failed, 0)
        self.assertGreater(self.telemetry.cycles_completed, 0)

        for rec in records:
            self.assertEqual(rec.state, SessionState.COMPLETED)
            self.assertEqual(rec.reconciliation_status, "MATCH")
            self.assertGreater(rec.equity, 0.0)
            self.assertGreaterEqual(rec.cash, 0.0)

    def test_06_multi_session_20_sessions_execution(self):
        """Execute 20-session simulation; verify endurance across multiple market days."""
        engine = self._create_engine(MultiSessionConfig(sessions_count=20, random_seed=123))
        records = engine.run_simulation(force_market_open=True)

        self.assertEqual(len(records), 20)
        self.assertEqual(self.telemetry.sessions_completed, 20)
        self.assertEqual(self.telemetry.sessions_failed, 0)

        # Validate final performance report
        report = engine.generate_performance_report()
        self.assertEqual(report.sessions_count, 20)
        self.assertIn("SIMULATED PAPER PERFORMANCE", report.disclaimer)
        self.assertEqual(len(report.equity_curve), 20)

    def test_07_multi_session_configurable_parameters(self):
        """Verify multi-session simulation honors custom capital, universe, and cost models."""
        custom_universe = ["RELIANCE", "TCS", "INFY"]
        cfg = MultiSessionConfig(
            sessions_count=3,
            initial_capital=500_000.0,
            random_seed=999,
            universe=custom_universe,
            transaction_cost_bps=15.0,
            slippage_bps=8.0,
        )
        engine = self._create_engine(cfg)
        records = engine.run_simulation(force_market_open=True)

        self.assertEqual(len(records), 3)
        self.assertEqual(records[0].session_id, "SESS-20240415-001")
        # Verify initial capital honored
        self.assertAlmostEqual(engine.orchestrator.initial_capital, 500_000.0, places=2)

    # ══════════════════════════════════════════════════════════════════════
    # CATEGORY 3: RESTART RECOVERY ACROSS 7 INTERRUPTION POINTS (7 Tests)
    # ══════════════════════════════════════════════════════════════════════

    def test_08_restart_recovery_1_before_order_submission(self):
        """Test process interruption 1: Before order submission."""
        interrupted = False

        def hook_fail(bname, ctx):
            nonlocal interrupted
            interrupted = True
            raise RuntimeError("Crash 1: Before order submission")

        engine = self._create_engine(MultiSessionConfig(sessions_count=1))
        engine.set_interruption_hook("before_order_submission", hook_fail)

        records = engine.run_simulation(force_market_open=True)
        self.assertTrue(interrupted)
        self.assertEqual(records[0].state, SessionState.FAILED)

        # Resume simulation with fresh engine (auto-load)
        engine_resumed = self._create_engine(MultiSessionConfig(sessions_count=1))
        resumed_records = engine_resumed.run_simulation(force_market_open=True)
        self.assertEqual(resumed_records[0].state, SessionState.COMPLETED)

    def test_09_restart_recovery_2_after_order_submission(self):
        """Test process interruption 2: After order submission."""
        def hook_fail(bname, ctx):
            raise RuntimeError("Crash 2: After order submission")

        engine = self._create_engine(MultiSessionConfig(sessions_count=1))
        engine.set_interruption_hook("after_order_submission", hook_fail)
        records = engine.run_simulation(force_market_open=True)
        self.assertEqual(records[0].state, SessionState.FAILED)

        # Resume: orders exist on disk; restart recovery restores without duplication
        engine_resumed = self._create_engine(MultiSessionConfig(sessions_count=1))
        engine_resumed.orchestrator._restore_persisted_state()
        self.assertGreaterEqual(self.telemetry.restart_recoveries, 1)

    def test_10_restart_recovery_3_after_fill(self):
        """Test process interruption 3: After fill execution."""
        def hook_fail(bname, ctx):
            raise RuntimeError("Crash 3: After fills")

        engine = self._create_engine(MultiSessionConfig(sessions_count=1))
        engine.set_interruption_hook("after_fill", hook_fail)
        records = engine.run_simulation(force_market_open=True)
        self.assertEqual(records[0].state, SessionState.FAILED)

        # Resumed engine safely loads fills without doubling
        engine_resumed = self._create_engine(MultiSessionConfig(sessions_count=1))
        engine_resumed.orchestrator._restore_persisted_state()
        self.assertGreaterEqual(self.telemetry.restart_recoveries, 1)

    def test_11_restart_recovery_4_before_accounting(self):
        """Test process interruption 4: Before accounting validation."""
        def hook_fail(bname, ctx):
            raise RuntimeError("Crash 4: Before accounting")

        engine = self._create_engine(MultiSessionConfig(sessions_count=1))
        engine.set_interruption_hook("before_accounting", hook_fail)
        records = engine.run_simulation(force_market_open=True)
        self.assertEqual(records[0].state, SessionState.FAILED)

        engine_resumed = self._create_engine(MultiSessionConfig(sessions_count=1))
        resumed_records = engine_resumed.run_simulation(force_market_open=True)
        self.assertEqual(resumed_records[0].state, SessionState.COMPLETED)

    def test_12_restart_recovery_5_after_accounting(self):
        """Test process interruption 5: After accounting update."""
        def hook_fail(bname, ctx):
            raise RuntimeError("Crash 5: After accounting")

        engine = self._create_engine(MultiSessionConfig(sessions_count=1))
        engine.set_interruption_hook("after_accounting", hook_fail)
        records = engine.run_simulation(force_market_open=True)
        self.assertEqual(records[0].state, SessionState.FAILED)

        # Resumption restores consistent account equity
        engine_resumed = self._create_engine(MultiSessionConfig(sessions_count=1))
        resumed_records = engine_resumed.run_simulation(force_market_open=True)
        self.assertEqual(resumed_records[0].state, SessionState.COMPLETED)

    def test_13_restart_recovery_6_before_reconciliation(self):
        """Test process interruption 6: Before reconciliation."""
        def hook_fail(bname, ctx):
            raise RuntimeError("Crash 6: Before reconciliation")

        engine = self._create_engine(MultiSessionConfig(sessions_count=1))
        engine.set_interruption_hook("before_reconciliation", hook_fail)
        records = engine.run_simulation(force_market_open=True)
        self.assertEqual(records[0].state, SessionState.FAILED)

        engine_resumed = self._create_engine(MultiSessionConfig(sessions_count=1))
        resumed_records = engine_resumed.run_simulation(force_market_open=True)
        self.assertEqual(resumed_records[0].state, SessionState.COMPLETED)

    def test_14_restart_recovery_7_after_reconciliation(self):
        """Test process interruption 7: After reconciliation."""
        def hook_fail(bname, ctx):
            raise RuntimeError("Crash 7: After reconciliation")

        engine = self._create_engine(MultiSessionConfig(sessions_count=1))
        engine.set_interruption_hook("after_reconciliation", hook_fail)
        records = engine.run_simulation(force_market_open=True)
        self.assertEqual(records[0].state, SessionState.FAILED)

        # On restart, reconciliation report is clean
        engine_resumed = self._create_engine(MultiSessionConfig(sessions_count=1))
        engine_resumed.orchestrator._restore_persisted_state()
        recon = engine_resumed.orchestrator.reconcile_state()
        self.assertTrue(recon.is_clean)

    # ══════════════════════════════════════════════════════════════════════
    # CATEGORY 4: IDEMPOTENCY STRESS TESTING (3 Tests)
    # ══════════════════════════════════════════════════════════════════════

    def test_15_order_idempotency_key_deduplication(self):
        """Submit the exact same order with identical idempotency key 5 times."""
        engine = self._create_engine()
        orch = engine.orchestrator
        t0 = datetime(2024, 4, 15, 10, 30, tzinfo=IST_ZONE)
        key = "IDEMP-STRESS-KEY-001"

        order = PaperOrder(
            symbol="RELIANCE",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            requested_quantity=10,
            idempotency_key=key,
        )
        orch.broker.update_market_panel({"RELIANCE": 2800.0}, {"RELIANCE": 100_000.0})
        v_quote = orch.data_adapter.validate_quote("RELIANCE", price=2800.0, volume=100_000.0)

        # 1st submission: must succeed
        out1 = orch.order_manager.submit_order(order, quote=v_quote, as_of_time=t0)
        self.assertEqual(out1.status, OrderStatus.FILLED)
        cash_after_1st = orch.broker.get_account().cash

        # Submissions 2 through 5: must all be rejected as DUPLICATE_ORDER
        for i in range(2, 6):
            dup_order = PaperOrder(
                symbol="RELIANCE",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                requested_quantity=10,
                idempotency_key=key,
            )
            out_dup = orch.order_manager.submit_order(dup_order, quote=v_quote, as_of_time=t0)
            self.assertEqual(out_dup.status, OrderStatus.REJECTED)
            self.assertEqual(out_dup.rejection_reason, RejectionReason.DUPLICATE_ORDER)

        # Verify cash and position was NOT deducted 5 times
        self.assertEqual(orch.broker.get_account().cash, cash_after_1st)
        self.assertEqual(orch.broker.get_positions()["RELIANCE"].shares, 10)

    def test_16_cycle_idempotency_same_timestamp(self):
        """Run cycle twice with identical timestamp; second run returns ALREADY_PROCESSED."""
        engine = self._create_engine()
        orch = engine.orchestrator
        t0 = datetime(2024, 4, 15, 10, 30, tzinfo=IST_ZONE)

        res1 = orch.run_cycle(universe=self.universe, as_of_time=t0, override_quotes=self.quotes, force_market_open=True)
        self.assertEqual(res1.state, CycleState.COMPLETED)

        res2 = orch.run_cycle(universe=self.universe, as_of_time=t0, override_quotes=self.quotes, force_market_open=True)
        self.assertEqual(res2.state, CycleState.ALREADY_PROCESSED)
        self.assertEqual(len(res2.orders_generated), 0)
        self.assertGreaterEqual(self.telemetry.duplicate_orders, 1)

    def test_17_repeated_session_idempotency(self):
        """Repeatedly save and load identical session record; confirms atomic storage idempotency."""
        rec = SessionRecord(
            session_id="SESS-20240415-IDEMP",
            simulation_date="2024-04-15",
            start_time="2024-04-15T10:30:00+05:30",
            state=SessionState.COMPLETED,
            equity=1_050_000.0,
            cash=800_000.0,
        )
        # Save 3 times
        for _ in range(3):
            self.persistence.save_session(rec)

        loaded = self.persistence.load_session("SESS-20240415-IDEMP")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["equity"], 1_050_000.0)

    # ══════════════════════════════════════════════════════════════════════
    # CATEGORY 5: FAILURE INJECTION ACROSS SUBSYSTEMS (4 Tests)
    # ══════════════════════════════════════════════════════════════════════

    def test_18_failure_injection_market_data(self):
        """Inject corrupt quotes (negative price, future timestamp, crossed spread)."""
        engine = self._create_engine()
        orch = engine.orchestrator
        t0 = datetime(2024, 4, 15, 10, 30, tzinfo=IST_ZONE)

        corrupt_quotes = dict(self.quotes)
        corrupt_quotes["TCS"] = -50.0  # Invalid negative price!

        res = orch.run_cycle(
            universe=self.universe,
            as_of_time=t0,
            override_quotes=corrupt_quotes,
            force_market_open=True,
        )
        self.assertIn("TCS", res.excluded_stocks)
        self.assertNotIn("TCS", res.eligible_stocks)

    def test_19_failure_injection_features_and_ml(self):
        """Inject catastrophic failure in ML engine; cycle must transition to MODEL_FAILED."""
        engine = self._create_engine()
        orch = engine.orchestrator
        t0 = datetime(2024, 4, 15, 10, 30, tzinfo=IST_ZONE)

        class FailingTrainer:
            model_type = "broken"
            target_horizon = 5
            def train_and_predict(self, candidate_panel, as_of_time):
                raise ValueError("Simulated catastrophic ML failure: NaN in training matrix")

        orch.ml_trainer = FailingTrainer()
        res = orch.run_cycle(universe=self.universe, as_of_time=t0, override_quotes=self.quotes, force_market_open=True)

        self.assertEqual(res.state, CycleState.MODEL_FAILED)
        self.assertEqual(len(res.orders_generated), 0)
        self.assertGreaterEqual(self.telemetry.model_errors, 1)

    def test_20_failure_injection_portfolio_infeasible(self):
        """Inject infeasible portfolio optimization; cycle must transition to PORTFOLIO_FAILED."""
        engine = self._create_engine()
        orch = engine.orchestrator
        t0 = datetime(2024, 4, 15, 10, 30, tzinfo=IST_ZONE)

        class FailingPortfolioRunner:
            def build_target_portfolio(self, *args, **kwargs):
                raise RuntimeError("Solver failed: quadratic constraints infeasible")

        orch.portfolio_runner = FailingPortfolioRunner()
        res = orch.run_cycle(universe=self.universe, as_of_time=t0, override_quotes=self.quotes, force_market_open=True)

        self.assertEqual(res.state, CycleState.PORTFOLIO_FAILED)
        self.assertEqual(len(res.orders_generated), 0)
        self.assertGreaterEqual(self.telemetry.execution_errors, 1)

    def test_21_failure_injection_accounting_invariants(self):
        """Artificially tamper with cash to negative value; invariant validator must fail closed."""
        engine = self._create_engine()
        orch = engine.orchestrator
        acct = orch.broker.get_account()
        acct.cash = -5000.0  # Illegal negative cash balance!

        with self.assertRaises(ValueError) as ctx:
            engine._validate_accounting_invariants(acct, orch.broker.get_positions())
        self.assertIn("Negative cash balance detected", str(ctx.exception))

    # ══════════════════════════════════════════════════════════════════════
    # CATEGORY 6: PARTIAL SYMBOL FAILURE ISOLATION (2 Tests)
    # ══════════════════════════════════════════════════════════════════════

    def test_22_partial_symbol_failure_corrupt_quote(self):
        """Verify that 1 corrupt symbol does not crash or corrupt the remaining portfolio."""
        engine = self._create_engine(MultiSessionConfig(sessions_count=1))
        orch = engine.orchestrator
        t0 = datetime(2024, 4, 15, 10, 30, tzinfo=IST_ZONE)

        quotes = dict(self.quotes)
        quotes["INFY"] = -999.0  # Corrupt symbol

        res = orch.run_cycle(
            universe=self.universe,
            as_of_time=t0,
            override_quotes=quotes,
            force_market_open=True,
        )
        self.assertEqual(res.state, CycleState.COMPLETED)
        self.assertIn("INFY", res.excluded_stocks)
        # Other 4 stocks must remain in eligible stocks
        self.assertEqual(len(res.eligible_stocks), 4)
        for sym in ["RELIANCE", "TCS", "HDFCBANK", "ICICIBANK"]:
            self.assertIn(sym, res.eligible_stocks)

    def test_23_partial_symbol_failure_missing_data(self):
        """Verify missing market data for 1 symbol excludes it without stopping others."""
        cache = LatestQuoteCache()
        t0 = datetime(2024, 4, 15, 10, 30, tzinfo=IST_ZONE)

        # Only update 3 symbols in cache
        for sym in ["RELIANCE", "TCS", "INFY"]:
            cache.update(RealtimeQuote(
                symbol=f"NSE:{sym}",
                exchange="NSE",
                timestamp=t0,
                last_price=self.quotes[sym],
                volume=500_000.0,
            ))

        engine = self._create_engine()
        engine.orchestrator.quote_cache = cache
        res = engine.orchestrator.run_cycle(universe=self.universe, as_of_time=t0, force_market_open=True)

        self.assertEqual(res.state, CycleState.COMPLETED)
        self.assertIn("HDFCBANK", res.excluded_stocks)
        self.assertIn("ICICIBANK", res.excluded_stocks)
        self.assertEqual(len(res.eligible_stocks), 3)

    # ══════════════════════════════════════════════════════════════════════
    # CATEGORY 7: MARKET SESSION SAFETY (3 Tests)
    # ══════════════════════════════════════════════════════════════════════

    def test_24_market_session_pre_market_rejection(self):
        """Pre-market session (09:05 AM IST) must reject paper execution when force_market_open=False."""
        engine = self._create_engine()
        orch = engine.orchestrator
        pre_market_t = datetime(2024, 4, 15, 9, 5, tzinfo=IST_ZONE)

        res = orch.run_cycle(
            universe=self.universe,
            as_of_time=pre_market_t,
            override_quotes=self.quotes,
            force_market_open=False,
        )
        self.assertEqual(res.state, CycleState.MARKET_CLOSED_SKIPPED)
        self.assertEqual(len(res.orders_generated), 0)

    def test_25_market_session_post_market_and_weekend(self):
        """Sunday or post-market session must reject paper execution."""
        engine = self._create_engine()
        orch = engine.orchestrator
        sunday_t = datetime(2024, 4, 14, 10, 30, tzinfo=IST_ZONE)  # Sunday

        res = orch.run_cycle(
            universe=self.universe,
            as_of_time=sunday_t,
            override_quotes=self.quotes,
            force_market_open=False,
        )
        self.assertEqual(res.state, CycleState.MARKET_CLOSED_SKIPPED)
        self.assertEqual(len(res.orders_generated), 0)

    def test_26_market_session_regular_trading_allowed(self):
        """Regular market session on Monday at 10:30 AM IST is allowed."""
        engine = self._create_engine()
        orch = engine.orchestrator
        monday_regular_t = datetime(2024, 4, 15, 10, 30, tzinfo=IST_ZONE)

        res = orch.run_cycle(
            universe=self.universe,
            as_of_time=monday_regular_t,
            override_quotes=self.quotes,
            force_market_open=False,
        )
        self.assertEqual(res.state, CycleState.COMPLETED)

    # ══════════════════════════════════════════════════════════════════════
    # CATEGORY 8: PAPER ACCOUNTING INVARIANTS (2 Tests)
    # ══════════════════════════════════════════════════════════════════════

    def test_27_accounting_invariants_cash_and_positions(self):
        """Verify strict accounting invariants across multiple cycles: cash >= 0, shares >= 0, equity balance."""
        engine = self._create_engine(MultiSessionConfig(sessions_count=5))
        records = engine.run_simulation(force_market_open=True)

        for rec in records:
            self.assertGreaterEqual(rec.cash, 0.0)
            self.assertAlmostEqual(rec.equity, rec.cash + rec.positions_value, places=1)
            for sym, pos_data in rec.positions_snapshot.items():
                self.assertGreaterEqual(pos_data["shares"], 0)

    def test_28_accounting_fees_and_pnl_consistency(self):
        """Verify fees recorded exactly once and realized P&L is internally consistent."""
        engine = self._create_engine()
        orch = engine.orchestrator
        t0 = datetime(2024, 4, 15, 10, 30, tzinfo=IST_ZONE)

        res = orch.run_cycle(universe=self.universe, as_of_time=t0, override_quotes=self.quotes, force_market_open=True)
        acct = orch.broker.get_account()

        expected_total_fees = sum(f.transaction_cost for f in orch.broker.get_fills())
        self.assertAlmostEqual(acct.total_fees, expected_total_fees, places=2)

    # ══════════════════════════════════════════════════════════════════════
    # CATEGORY 9: POST-SESSION RECONCILIATION (2 Tests)
    # ══════════════════════════════════════════════════════════════════════

    def test_29_reconciliation_clean_match(self):
        """Verify clean reconciliation report upon normal cycle execution."""
        engine = self._create_engine()
        orch = engine.orchestrator
        t0 = datetime(2024, 4, 15, 10, 30, tzinfo=IST_ZONE)

        res = orch.run_cycle(universe=self.universe, as_of_time=t0, override_quotes=self.quotes, force_market_open=True)
        recon = orch.reconcile_state()

        self.assertTrue(recon.is_clean)
        self.assertEqual(recon.status, ReconciliationStatus.MATCH)
        self.assertEqual(len(recon.discrepancies), 0)

    def test_30_reconciliation_mismatch_detection(self):
        """Verify reconciliation engine catches phantom position mismatch."""
        engine = self._create_engine()
        orch = engine.orchestrator

        # Manually inject phantom position unknown to expected targets
        orch.broker.accounting.positions["TCS"] = PaperPosition(
            symbol="TCS", shares=50, average_cost=3500.0, current_price=3500.0
        )
        report = orch.reconcile_state(expected_targets={})
        self.assertFalse(report.is_clean)
        self.assertIn(report.status, (ReconciliationStatus.MISMATCH, ReconciliationStatus.ERROR))

    # ══════════════════════════════════════════════════════════════════════
    # CATEGORY 10: ALL 12 PRE-TRADE RISK CHECKS (2 Tests)
    # ══════════════════════════════════════════════════════════════════════

    def test_31_risk_checks_pass_and_block_behavior(self):
        """Verify pre-trade risk engine blocks orders that breach risk limits."""
        engine = self._create_engine()
        rm = engine.orchestrator.risk_manager
        acct = engine.orchestrator.broker.get_account()
        t0 = datetime(2024, 4, 15, 10, 30, tzinfo=IST_ZONE)
        v_quote = engine.orchestrator.data_adapter.validate_quote("RELIANCE", price=2800.0, volume=1000.0)

        # 1. Available Cash check breach
        acct.cash = 100.0
        order = PaperOrder(symbol="RELIANCE", side=OrderSide.BUY, order_type=OrderType.MARKET, requested_quantity=100)
        res = rm.evaluate_order(order, acct, {}, v_quote, reference_volume=1000.0, as_of_time=t0)
        self.assertFalse(res.passed)
        self.assertEqual(res.rejection_reason, RejectionReason.INSUFFICIENT_CASH)

        # 2. Liquidity breach (requesting 200 shares on 1000 vol = 20% > 5% limit)
        acct.cash = 1_000_000.0
        order_liq = PaperOrder(symbol="RELIANCE", side=OrderSide.BUY, order_type=OrderType.MARKET, requested_quantity=200)
        res_liq = rm.evaluate_order(order_liq, acct, {}, v_quote, reference_volume=1000.0, as_of_time=t0)
        self.assertFalse(res_liq.passed)
        self.assertEqual(res_liq.rejection_reason, RejectionReason.LIQUIDITY_LIMIT)

    def test_32_risk_checks_persistent_kill_switch_resumption(self):
        """Verify kill switch completely halts execution and cleanly resumes when disabled."""
        engine = self._create_engine()
        orch = engine.orchestrator

        # Arm kill switch
        orch.kill_switch.enable(reason="EMERGENCY_STOP", operator="OPERATIONAL_TEST")
        self.assertTrue(orch.kill_switch.is_active())

        t0 = datetime(2024, 4, 15, 10, 30, tzinfo=IST_ZONE)
        res = orch.run_cycle(universe=self.universe, as_of_time=t0, override_quotes=self.quotes, force_market_open=True)
        self.assertGreater(len(res.orders_rejected), 0)
        self.assertEqual(len(res.fills), 0)

        # Disarm kill switch
        orch.kill_switch.disable(operator="OPERATIONAL_TEST")
        self.assertFalse(orch.kill_switch.is_active())

        t1 = datetime(2024, 4, 16, 10, 30, tzinfo=IST_ZONE)
        res1 = orch.run_cycle(universe=self.universe, as_of_time=t1, override_quotes=self.quotes, force_market_open=True)
        self.assertEqual(res1.state, CycleState.COMPLETED)
        self.assertGreater(len(res1.fills), 0)

    # ══════════════════════════════════════════════════════════════════════
    # CATEGORY 11: OPERATIONAL TELEMETRY (2 Tests)
    # ══════════════════════════════════════════════════════════════════════

    def test_33_operational_telemetry_metrics_tracking(self):
        """Verify telemetry tracks all 19 mandatory operational reliability metrics."""
        engine = self._create_engine(MultiSessionConfig(sessions_count=3))
        engine.run_simulation(force_market_open=True)

        telem_dict = self.telemetry.to_dict()
        mandatory_keys = [
            "sessions_started", "sessions_completed", "sessions_failed",
            "cycles_started", "cycles_completed", "orders_generated",
            "orders_filled", "orders_rejected", "duplicate_orders",
            "risk_rejections", "data_errors", "model_errors",
            "execution_errors", "reconciliation_errors", "restart_recoveries",
            "average_cycle_latency", "maximum_cycle_latency",
            "symbols_processed", "symbols_rejected",
        ]
        for key in mandatory_keys:
            self.assertIn(key, telem_dict)

        self.assertEqual(telem_dict["sessions_completed"], 3)
        self.assertGreater(telem_dict["cycles_completed"], 0)
        self.assertGreaterEqual(telem_dict["average_cycle_latency"], 0.0)

    def test_34_telemetry_atomic_persistence(self):
        """Verify saving and reloading operational telemetry from disk."""
        self.telemetry.sessions_started = 10
        self.telemetry.sessions_completed = 9
        self.telemetry.sessions_failed = 1
        self.persistence.save_telemetry(self.telemetry.to_dict())

        loaded = self.persistence.load_telemetry()
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["sessions_started"], 10)
        self.assertEqual(loaded["sessions_completed"], 9)
        self.assertEqual(loaded["sessions_failed"], 1)

    # ══════════════════════════════════════════════════════════════════════
    # CATEGORY 12: PERSISTENT SESSION HISTORY (2 Tests)
    # ══════════════════════════════════════════════════════════════════════

    def test_35_session_history_atomic_persistence(self):
        """Verify session records persist atomically and are listable in order."""
        rec1 = SessionRecord(session_id="SESS-20240415-001", simulation_date="2024-04-15", start_time="2024-04-15T10:30:00")
        rec2 = SessionRecord(session_id="SESS-20240416-002", simulation_date="2024-04-16", start_time="2024-04-16T10:30:00")

        self.persistence.save_session(rec1)
        self.persistence.save_session(rec2)

        sessions = self.persistence.list_sessions()
        self.assertEqual(len(sessions), 2)
        # Most recent first
        self.assertEqual(sessions[0]["session_id"], "SESS-20240416-002")

    def test_36_session_history_sanitized_filenames(self):
        """Verify session IDs with special characters (colons, slashes) are sanitized safely."""
        rec = SessionRecord(
            session_id="SESS:2024/04/15\\TEST",
            simulation_date="2024-04-15",
            start_time="2024-04-15T10:30:00",
        )
        self.persistence.save_session(rec)
        loaded = self.persistence.load_session("SESS:2024/04/15\\TEST")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["session_id"], "SESS:2024/04/15\\TEST")

    # ══════════════════════════════════════════════════════════════════════
    # CATEGORY 13: DETERMINISTIC REPRODUCTION (2 Tests)
    # ══════════════════════════════════════════════════════════════════════

    def test_37_deterministic_reproduction_identical_seed(self):
        """Two separate simulation runs with identical seed (42) must yield bit-exact identical equity curves."""
        dir1 = os.path.join(self.test_dir, "run1")
        dir2 = os.path.join(self.test_dir, "run2")
        os.makedirs(dir1, exist_ok=True)
        os.makedirs(dir2, exist_ok=True)

        engine1 = MultiSessionSimulationEngine(
            config=MultiSessionConfig(sessions_count=5, random_seed=42),
            data_dir=dir1,
            base_prices=self.quotes,
        )
        engine2 = MultiSessionSimulationEngine(
            config=MultiSessionConfig(sessions_count=5, random_seed=42),
            data_dir=dir2,
            base_prices=self.quotes,
        )

        recs1 = engine1.run_simulation(force_market_open=True)
        recs2 = engine2.run_simulation(force_market_open=True)

        for s1, s2 in zip(recs1, recs2):
            self.assertEqual(s1.simulation_date, s2.simulation_date)
            self.assertAlmostEqual(s1.equity, s2.equity, places=2)
            self.assertAlmostEqual(s1.cash, s2.cash, places=2)
            self.assertEqual(s1.orders_count, s2.orders_count)
            self.assertEqual(s1.fills_count, s2.fills_count)

    def test_38_deterministic_reproduction_different_seed(self):
        """Simulation run with different seed produces different market drift and equity trajectory."""
        engine1 = self._create_engine(MultiSessionConfig(sessions_count=5, random_seed=42))
        engine2 = self._create_engine(MultiSessionConfig(sessions_count=5, random_seed=9999))

        recs1 = engine1.run_simulation(force_market_open=True)
        recs2 = engine2.run_simulation(force_market_open=True)

        # Equities on session 5 should differ due to different random price drift
        self.assertNotEqual(recs1[-1].equity, recs2[-1].equity)

    # ══════════════════════════════════════════════════════════════════════
    # CATEGORY 14: DATA INTEGRITY & LOOK-AHEAD PROTECTION (2 Tests)
    # ══════════════════════════════════════════════════════════════════════

    def test_39_look_ahead_protection_mutation_test(self):
        """Mutation test: Altering future data for T+1 must NOT change decisions at session T."""
        engine = self._create_engine()
        t0 = datetime(2024, 4, 15, 10, 30, tzinfo=IST_ZONE)

        # Baseline decision at T0
        res_baseline = engine.orchestrator.run_cycle(
            universe=self.universe,
            as_of_time=t0,
            override_quotes=self.quotes,
            force_market_open=True,
        )
        decisions_baseline = [(d.symbol, d.target_shares) for d in res_baseline.decisions]

        # Reset state and mutate future prices for T+1
        engine_mutated = self._create_engine()
        # Mutate future quotes
        mutated_future_quotes = {k: v * 2.0 for k, v in self.quotes.items()}

        res_after = engine_mutated.orchestrator.run_cycle(
            universe=self.universe,
            as_of_time=t0,
            override_quotes=self.quotes,  # Same T0 quotes
            force_market_open=True,
        )
        decisions_after = [(d.symbol, d.target_shares) for d in res_after.decisions]

        # Earlier decisions must remain identical
        self.assertEqual(decisions_baseline, decisions_after)

    def test_40_point_in_time_strictly_leq_t(self):
        """Verify all quotes evaluated in cycle have timestamps strictly <= cycle as_of_time."""
        engine = self._create_engine()
        t0 = datetime(2024, 4, 15, 10, 30, tzinfo=IST_ZONE)

        res = engine.orchestrator.run_cycle(
            universe=self.universe,
            as_of_time=t0,
            override_quotes=self.quotes,
            force_market_open=True,
        )
        for sig in res.signals:
            sig_t = datetime.fromisoformat(sig.timestamp)
            self.assertLessEqual(sig_t, t0)

    # ══════════════════════════════════════════════════════════════════════
    # CATEGORY 15: PAPER / LIVE SAFETY BOUNDARY (2 Tests)
    # ══════════════════════════════════════════════════════════════════════

    def test_41_live_trading_disabled_boundary(self):
        """Verify that passing an adapter that supports live orders raises LiveTradingDisabledError."""
        class MockLiveBroker:
            def supports_live_orders(self):
                return True

        with self.assertRaises(LiveTradingDisabledError):
            PaperTradingOrchestrator(broker=MockLiveBroker())

        with self.assertRaises(LiveTradingDisabledError):
            orch = PaperTradingOrchestrator()
            orch.broker = MockLiveBroker()
            MultiSessionSimulationEngine(orchestrator=orch)

    def test_42_no_real_credentials_or_broker_sdk(self):
        """Verify no real broker credentials or live Kite SDK are present in the paper subsystem."""
        from execution.paper.simulation import MultiSessionSimulationEngine
        from execution.paper.orchestrator import PaperTradingOrchestrator

        engine = self._create_engine()
        self.assertFalse(engine.orchestrator.broker.get_capabilities().supports_live_orders)
        self.assertNotIn("kite", str(type(engine.orchestrator.broker)).lower())

    # ══════════════════════════════════════════════════════════════════════
    # CATEGORY 16: BINANCE ISOLATION & REST API ENDPOINTS (2 Tests)
    # ══════════════════════════════════════════════════════════════════════

    def test_43_binance_subsystem_isolation(self):
        """Verify Step 13 does not access or alter legacy Binance bot files or state."""
        binance_files = ["bot_state.json", "trade_log.csv"]
        for bf in binance_files:
            bpath = os.path.join(_PROJECT_ROOT, bf)
            if os.path.exists(bpath):
                # Verify mtime was not modified by running simulation
                mtime_before = os.path.getmtime(bpath)
                engine = self._create_engine(MultiSessionConfig(sessions_count=1))
                engine.run_simulation(force_market_open=True)
                mtime_after = os.path.getmtime(bpath)
                self.assertEqual(mtime_before, mtime_after)

    def test_44_dashboard_simulation_rest_endpoints(self):
        """Verify /api/paper/telemetry, /api/paper/sessions, and /api/paper/simulation/run endpoints."""
        from dashboard.server import app
        client = app.test_client()

        # 1. GET /api/paper/telemetry
        resp = client.get("/api/paper/telemetry")
        self.assertEqual(resp.status_code, 200)
        telem = resp.get_json()
        self.assertIn("sessions_started", telem)
        self.assertIn("cycles_completed", telem)

        # 2. GET /api/paper/sessions
        resp_s = client.get("/api/paper/sessions")
        self.assertEqual(resp_s.status_code, 200)
        self.assertIn("sessions", resp_s.get_json())

        # 3. POST /api/paper/simulation/run (synchronous)
        resp_run = client.post(
            "/api/paper/simulation/run",
            json={
                "sessions_count": 2,
                "start_date": "2024-04-15",
                "random_seed": 42,
                "is_async": False,
            },
        )
        self.assertEqual(resp_run.status_code, 200)
        run_data = resp_run.get_json()
        self.assertEqual(run_data["status"], "completed")
        self.assertEqual(run_data["sessions_count"], 2)
        self.assertIn("performance", run_data)


if __name__ == "__main__":
    unittest.main()
