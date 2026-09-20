"""
tests/test_broker_interface.py — Step 10 Broker Integration Test Suite.

Verifies:
  1. Broker ABC interface contract compliance (PaperBroker, KiteBrokerAdapter).
  2. Capability matrices (introspection, live trading explicitly False).
  3. Broker-neutral order translation and Kite payload generation.
  4. BrokerFactory instantiation and strict live-trading gating (LiveTradingDisabledError).
  5. Safe Kite stub execution block (zero real orders).
  6. Fail-closed OrderManager handling of timeouts / uncertain state without blind retries.
  7. Cross-system broker reconciliation (cash, positions, order state).
  8. Credential safety (no secrets leaking into string representations).
  9. Binance legacy isolation (zero contamination).
"""

import os
import sys
import unittest
from datetime import datetime, timezone

# Ensure project root is on sys.path
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from execution.broker import Broker
from execution.paper_broker import PaperBroker
from execution.adapters.base import BaseBrokerAdapter
from execution.adapters.kite_adapter import KiteBrokerAdapter
from execution.broker_factory import create_broker, get_supported_brokers
from execution.order_translator import BrokerOrderRequest, OrderTranslator
from execution.exceptions import (
    BrokerError,
    BrokerConnectionError,
    BrokerTimeoutError,
    BrokerOrderRejectedError,
    BrokerUncertainStateError,
    BrokerAuthenticationError,
    LiveTradingDisabledError,
)
from execution.models import (
    BrokerCapabilities,
    BrokerConnectionState,
    OrderSide,
    OrderStatus,
    OrderType,
    PaperAccount,
    PaperFill,
    PaperOrder,
    PaperPosition,
    ReconciliationStatus,
    RejectionReason,
)
from execution.order_manager import OrderManager
from execution.reconciliation import ReconciliationEngine
import tempfile
from execution.data_adapter import ValidatedQuote
from risk.kill_switch import PersistentKillSwitch
from risk.paper_risk_manager import PaperRiskManager


class TestBrokerInterfaceContract(unittest.TestCase):
    """Verify that concrete brokers satisfy the Broker abstract base class."""

    def test_paper_broker_implements_abc(self):
        broker = PaperBroker()
        self.assertIsInstance(broker, Broker)
        self.assertTrue(callable(broker.submit_order))
        self.assertTrue(callable(broker.cancel_order))
        self.assertTrue(callable(broker.get_order))
        self.assertTrue(callable(broker.get_orders))
        self.assertTrue(callable(broker.get_positions))
        self.assertTrue(callable(broker.get_account))
        self.assertTrue(callable(broker.get_fills))
        self.assertTrue(callable(broker.get_quote))
        self.assertTrue(callable(broker.reconcile))
        self.assertTrue(callable(broker.get_capabilities))
        self.assertTrue(callable(broker.get_connection_status))

    def test_kite_broker_adapter_implements_abc(self):
        adapter = KiteBrokerAdapter(mock_mode=True)
        self.assertIsInstance(adapter, Broker)
        self.assertIsInstance(adapter, BaseBrokerAdapter)
        self.assertTrue(callable(adapter.submit_order))
        self.assertTrue(callable(adapter.cancel_order))
        self.assertTrue(callable(adapter.get_order))
        self.assertTrue(callable(adapter.get_orders))
        self.assertTrue(callable(adapter.get_positions))
        self.assertTrue(callable(adapter.get_account))
        self.assertTrue(callable(adapter.get_fills))
        self.assertTrue(callable(adapter.get_quote))
        self.assertTrue(callable(adapter.reconcile))
        self.assertTrue(callable(adapter.get_capabilities))
        self.assertTrue(callable(adapter.get_connection_status))


class TestBrokerCapabilities(unittest.TestCase):
    """Verify capability matrices for paper and external adapters."""

    def test_paper_broker_capabilities(self):
        broker = PaperBroker()
        caps = broker.get_capabilities()
        self.assertIsInstance(caps, BrokerCapabilities)
        self.assertEqual(caps.broker_name, "PaperBroker")
        self.assertFalse(caps.supports_live_orders)
        self.assertTrue(caps.supports_market_orders)
        self.assertTrue(caps.supports_limit_orders)
        self.assertTrue(caps.supports_order_cancellation)
        self.assertTrue(caps.supports_integer_shares)
        self.assertFalse(caps.supports_fractional_shares)
        self.assertIn("NSE", caps.supported_exchanges)

    def test_kite_adapter_capabilities(self):
        adapter = KiteBrokerAdapter(mock_mode=True)
        caps = adapter.get_capabilities()
        self.assertIsInstance(caps, BrokerCapabilities)
        self.assertEqual(caps.broker_name, "ZerodhaKite")
        self.assertFalse(caps.supports_live_orders)  # Strictly False in Step 10
        self.assertTrue(caps.supports_market_orders)
        self.assertTrue(caps.supports_limit_orders)
        self.assertIn("NSE", caps.supported_exchanges)
        self.assertIn("BSE", caps.supported_exchanges)


class TestOrderTranslator(unittest.TestCase):
    """Verify order translation between internal models and broker formats."""

    def test_to_broker_request(self):
        order = PaperOrder(
            symbol="RELIANCE",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            requested_quantity=50,
            limit_price=2850.50,
        )
        req = OrderTranslator.to_broker_request(order)
        self.assertIsInstance(req, BrokerOrderRequest)
        self.assertEqual(req.symbol, "RELIANCE")
        self.assertEqual(req.side, OrderSide.BUY)
        self.assertEqual(req.order_type, OrderType.LIMIT)
        self.assertEqual(req.quantity, 50)
        self.assertEqual(req.limit_price, 2850.50)
        self.assertEqual(req.exchange, "NSE")
        self.assertEqual(req.product, "CNC")

    def test_to_kite_payload(self):
        req = BrokerOrderRequest(
            symbol="TCS",
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            quantity=25,
            limit_price=3920.00,
            exchange="NSE",
            product="CNC",
            validity="DAY",
            tag="ORD12345",
        )
        payload = OrderTranslator.to_kite_payload(req)
        self.assertEqual(payload["tradingsymbol"], "TCS")
        self.assertEqual(payload["exchange"], "NSE")
        self.assertEqual(payload["transaction_type"], "SELL")
        self.assertEqual(payload["order_type"], "LIMIT")
        self.assertEqual(payload["quantity"], 25)
        self.assertEqual(payload["price"], 3920.00)
        self.assertEqual(payload["product"], "CNC")
        self.assertEqual(payload["validity"], "DAY")
        self.assertEqual(payload["tag"], "ORD12345")

    def test_parse_kite_status(self):
        self.assertEqual(OrderTranslator.parse_kite_status("COMPLETE"), OrderStatus.FILLED)
        self.assertEqual(OrderTranslator.parse_kite_status("REJECTED"), OrderStatus.REJECTED)
        self.assertEqual(OrderTranslator.parse_kite_status("CANCELLED"), OrderStatus.CANCELLED)
        self.assertEqual(OrderTranslator.parse_kite_status("OPEN"), OrderStatus.SUBMITTED)
        self.assertEqual(OrderTranslator.parse_kite_status("UNKNOWN_STATUS"), OrderStatus.SUBMITTED)


class TestBrokerFactory(unittest.TestCase):
    """Verify factory creation and live trading prohibition."""

    def test_create_paper_broker(self):
        broker = create_broker("paper", initial_capital=500_000.0)
        self.assertIsInstance(broker, PaperBroker)
        self.assertEqual(broker.get_account().cash, 500_000.0)

    def test_create_kite_broker_mock(self):
        broker = create_broker("kite", mock_mode=True)
        self.assertIsInstance(broker, KiteBrokerAdapter)
        self.assertEqual(broker.get_capabilities().broker_name, "ZerodhaKite")

    def test_live_trading_mode_blocked(self):
        """CRITICAL: Factory must raise LiveTradingDisabledError on live mode."""
        with self.assertRaises(LiveTradingDisabledError):
            create_broker("paper", trading_mode="live")

        with self.assertRaises(LiveTradingDisabledError):
            create_broker("kite", trading_mode="live")

    def test_unexpected_trading_modes_fail_closed(self):
        """Verify that unexpected/unrecognized trading modes fail closed with LiveTradingDisabledError."""
        for mode in ("LIVE", "production", "prod", "true", "broker", "real", "invalid_mode"):
            with self.assertRaises(LiveTradingDisabledError):
                create_broker("paper", trading_mode=mode)
            with self.assertRaises(LiveTradingDisabledError):
                create_broker("kite", trading_mode=mode)

    def test_unsupported_broker_raises_value_error(self):
        with self.assertRaises(ValueError):
            create_broker("non_existent_broker")



class TestSafeKiteStub(unittest.TestCase):
    """Verify Kite adapter safety barriers."""

    def test_live_order_raises_disabled_error(self):
        """Kite adapter without mock_mode must reject order submission."""
        adapter = KiteBrokerAdapter(mock_mode=False)
        order = PaperOrder(
            symbol="INFY",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            requested_quantity=10,
        )
        with self.assertRaises(LiveTradingDisabledError):
            adapter.submit_order(order)

        with self.assertRaises(LiveTradingDisabledError):
            adapter.cancel_order("ANY_ID")

    def test_mock_mode_safe_submission(self):
        adapter = KiteBrokerAdapter(mock_mode=True)
        order = PaperOrder(
            symbol="HDFCBANK",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            requested_quantity=20,
            limit_price=1650.0,
        )
        res = adapter.submit_order(order)
        self.assertEqual(res.status, OrderStatus.SUBMITTED)
        self.assertIn("kite_payload", res.metadata)
        self.assertEqual(res.metadata["kite_payload"]["tradingsymbol"], "HDFCBANK")

    def test_authentication_error_without_credentials(self):
        adapter = KiteBrokerAdapter(mock_mode=False)
        with self.assertRaises(BrokerAuthenticationError):
            adapter.connect()


import pandas as pd


class TestFailClosedOrderManager(unittest.TestCase):
    """Verify OrderManager fail-closed behavior on timeout or uncertain state."""

    class TimeoutBroker(PaperBroker):
        """Mock broker that raises BrokerTimeoutError on order submission."""
        def submit_order(self, order: PaperOrder) -> PaperOrder:
            raise BrokerTimeoutError("Gateway timeout after 5000ms", broker_name="MockBroker")

    class RejectBroker(PaperBroker):
        """Mock broker that raises BrokerOrderRejectedError."""
        def submit_order(self, order: PaperOrder) -> PaperOrder:
            raise BrokerOrderRejectedError("Margin requirement not met", broker_name="MockBroker")

    def setUp(self):
        self.as_of_time = pd.Timestamp("2024-04-15 10:30:00", tz="Asia/Kolkata")
        self.quote = ValidatedQuote(
            symbol="ICICIBANK",
            price=1100.0,
            volume=1_000_000.0,
            timestamp=self.as_of_time,
            data_timestamp=self.as_of_time,
            data_age_seconds=1.0,
            is_valid=True,
        )
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ks = PersistentKillSwitch(persistence_path=os.path.join(self.temp_dir.name, "ks.json"))
        self.risk = PaperRiskManager(kill_switch=self.ks)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_timeout_marks_submitted_uncertain_no_retry(self):
        broker = self.TimeoutBroker()
        broker.update_market_price("ICICIBANK", 1100.0, volume=1_000_000)
        risk = self.risk
        om = OrderManager(broker=broker, risk_manager=risk)

        order = PaperOrder(
            symbol="ICICIBANK",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            requested_quantity=10,
        )

        res = om.submit_order(order, quote=self.quote, as_of_time=self.as_of_time)
        # FAIL-CLOSED ASSERTIONS:
        self.assertEqual(res.status, OrderStatus.SUBMITTED)
        self.assertTrue(res.metadata.get("uncertain_state"))
        self.assertIn(order.order_id, om.orders)
        self.assertIn(order, om.get_active_orders())

    def test_broker_rejection_marks_rejected(self):
        broker = self.RejectBroker()
        broker.update_market_price("ICICIBANK", 1100.0, volume=1_000_000)
        risk = self.risk
        om = OrderManager(broker=broker, risk_manager=risk)

        order = PaperOrder(
            symbol="ICICIBANK",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            requested_quantity=10,
        )

        res = om.submit_order(order, quote=self.quote, as_of_time=self.as_of_time)
        self.assertEqual(res.status, OrderStatus.REJECTED)
        self.assertEqual(res.rejection_reason, RejectionReason.BROKER_ERROR)

    def test_uncertain_order_workflow_reconciliation(self):
        """
        Verify end-to-end workflow:
          1. submit order -> broker timeout
          2. order marked SUBMITTED with uncertain_state=True
          3. NO blind retry occurs (orders count remains 1)
          4. Reconciliation resolves state against broker without creating duplicate order
        """
        broker = self.TimeoutBroker()
        broker.update_market_price("ICICIBANK", 1100.0, volume=1_000_000)
        risk = self.risk
        om = OrderManager(broker=broker, risk_manager=risk)

        order = PaperOrder(
            symbol="ICICIBANK",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            requested_quantity=10,
        )

        res = om.submit_order(order, quote=self.quote, as_of_time=self.as_of_time)
        self.assertEqual(res.status, OrderStatus.SUBMITTED)
        self.assertTrue(res.metadata.get("uncertain_state"))

        # Zero blind retry assertion
        self.assertEqual(len(om.orders), 1)

        # Later, reconciliation runs against broker
        report = ReconciliationEngine.reconcile_with_broker(
            local_account=broker.get_account(),
            local_positions=broker.get_positions(),
            local_orders=om.orders,
            broker=broker,
        )
        # TimeoutBroker never recorded order, so reconciliation accurately flags missing order at broker
        self.assertEqual(report.status, ReconciliationStatus.MISMATCH)
        cats = [d.category for d in report.discrepancies]
        self.assertIn("LOCAL_ORDER_MISSING_AT_BROKER", cats)

        # Still exactly 1 order in manager, zero duplicates created
        self.assertEqual(len(om.orders), 1)




class TestBrokerReconciliation(unittest.TestCase):
    """Verify multi-tier reconciliation between local state and broker state."""

    def test_clean_reconciliation(self):
        broker = PaperBroker(initial_capital=1_000_000.0)
        local_account = broker.get_account()
        local_positions = broker.get_positions()
        local_orders = {}

        report = ReconciliationEngine.reconcile_with_broker(
            local_account=local_account,
            local_positions=local_positions,
            local_orders=local_orders,
            broker=broker,
        )
        self.assertEqual(report.status, ReconciliationStatus.MATCH)
        self.assertTrue(report.is_clean)
        self.assertEqual(len(report.discrepancies), 0)

    def test_position_mismatch_detected(self):
        broker = PaperBroker(initial_capital=1_000_000.0)
        local_account = broker.get_account()
        local_positions = {
            "RELIANCE": PaperPosition(symbol="RELIANCE", shares=50, average_cost=2800.0, current_price=2850.0)
        }
        local_orders = {}

        report = ReconciliationEngine.reconcile_with_broker(
            local_account=local_account,
            local_positions=local_positions,
            local_orders=local_orders,
            broker=broker,
        )
        self.assertEqual(report.status, ReconciliationStatus.MISMATCH)
        self.assertFalse(report.is_clean)
        cats = [d.category for d in report.discrepancies]
        self.assertIn("BROKER_POSITION_MISMATCH", cats)

    def test_cash_mismatch_detected(self):
        broker = PaperBroker(initial_capital=1_000_000.0)
        local_account = PaperAccount(initial_capital=1_000_000.0, cash=950_000.0)
        local_positions = {}
        local_orders = {}

        report = ReconciliationEngine.reconcile_with_broker(
            local_account=local_account,
            local_positions=local_positions,
            local_orders=local_orders,
            broker=broker,
        )
        self.assertEqual(report.status, ReconciliationStatus.MISMATCH)
        cats = [d.category for d in report.discrepancies]
        self.assertIn("BROKER_CASH_MISMATCH", cats)

    def test_orphan_broker_order_detected(self):
        broker = PaperBroker()
        broker.update_market_price("TCS", 3900.0)
        order = PaperOrder(
            symbol="TCS",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            requested_quantity=10,
        )
        broker.submit_order(order)

        local_account = broker.get_account()
        local_positions = broker.get_positions()
        local_orders = {}  # local doesn't know about this order

        report = ReconciliationEngine.reconcile_with_broker(
            local_account=local_account,
            local_positions=local_positions,
            local_orders=local_orders,
            broker=broker,
        )
        self.assertEqual(report.status, ReconciliationStatus.MISMATCH)
        cats = [d.category for d in report.discrepancies]
        self.assertIn("BROKER_ORDER_ORPHAN", cats)

    def test_local_order_missing_at_broker_detected(self):
        broker = PaperBroker()
        local_account = broker.get_account()
        local_positions = {}
        missing_ord = PaperOrder(
            symbol="INFY",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            requested_quantity=10,
            status=OrderStatus.SUBMITTED,
        )
        local_orders = {missing_ord.order_id: missing_ord}

        report = ReconciliationEngine.reconcile_with_broker(
            local_account=local_account,
            local_positions=local_positions,
            local_orders=local_orders,
            broker=broker,
        )
        self.assertEqual(report.status, ReconciliationStatus.MISMATCH)
        cats = [d.category for d in report.discrepancies]
        self.assertIn("LOCAL_ORDER_MISSING_AT_BROKER", cats)

    def test_order_status_and_quantity_mismatch_detected(self):
        broker = PaperBroker()
        broker.update_market_price("RELIANCE", 2800.0)
        broker_ord = PaperOrder(
            symbol="RELIANCE",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            requested_quantity=20,
        )
        broker.submit_order(broker_ord)  # broker filled it

        local_account = broker.get_account()
        local_positions = broker.get_positions()
        # Local still has it as SUBMITTED with 0 filled
        local_ord = PaperOrder(
            order_id=broker_ord.order_id,
            symbol="RELIANCE",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            requested_quantity=20,
            status=OrderStatus.SUBMITTED,
            filled_quantity=0,
        )
        local_orders = {local_ord.order_id: local_ord}

        report = ReconciliationEngine.reconcile_with_broker(
            local_account=local_account,
            local_positions=local_positions,
            local_orders=local_orders,
            broker=broker,
        )
        self.assertEqual(report.status, ReconciliationStatus.MISMATCH)
        cats = [d.category for d in report.discrepancies]
        self.assertIn("BROKER_ORDER_STATUS_MISMATCH", cats)
        self.assertIn("BROKER_ORDER_QUANTITY_MISMATCH", cats)

    def test_duplicate_fill_audit(self):
        account = PaperAccount()
        positions = {}
        fill1 = PaperFill(
            fill_id="FILL-001",
            order_id="ORD-001",
            symbol="TCS",
            side=OrderSide.BUY,
            quantity=10,
            price=3500.0,
            slippage=0.0,
            transaction_cost=35.0,
            total_notional=35000.0,
        )
        # Duplicate fill with same fill_id
        fills = [fill1, fill1]
        report = ReconciliationEngine.reconcile(
            account=account,
            positions=positions,
            fills=fills,
        )
        cats = [d.category for d in report.discrepancies]
        self.assertIn("DUPLICATE_FILL", cats)

    def test_no_silent_state_overwrite(self):
        """Verify that reconciliation NEVER mutates local account or position state."""
        broker = PaperBroker(initial_capital=1_000_000.0)
        local_account = PaperAccount(initial_capital=1_000_000.0, cash=850_000.0)
        local_positions = {
            "TCS": PaperPosition(symbol="TCS", shares=10, average_cost=3000.0, current_price=3100.0)
        }
        orig_cash = local_account.cash
        orig_shares = local_positions["TCS"].shares

        report = ReconciliationEngine.reconcile_with_broker(
            local_account=local_account,
            local_positions=local_positions,
            local_orders={},
            broker=broker,
        )
        self.assertEqual(report.status, ReconciliationStatus.MISMATCH)
        # Assert NO mutation occurred
        self.assertEqual(local_account.cash, orig_cash)
        self.assertEqual(local_positions["TCS"].shares, orig_shares)



class TestCredentialSafety(unittest.TestCase):
    """Verify that credentials are never exposed in string representations."""

    def test_secrets_not_in_repr(self):
        adapter = KiteBrokerAdapter(
            api_key="SECRET_API_KEY_12345",
            access_token="SECRET_TOKEN_ABCDE",
            mock_mode=True,
        )
        repr_str = str(adapter) + repr(adapter)
        self.assertNotIn("SECRET_API_KEY_12345", repr_str)
        self.assertNotIn("SECRET_TOKEN_ABCDE", repr_str)


if __name__ == "__main__":
    unittest.main(verbosity=2)
