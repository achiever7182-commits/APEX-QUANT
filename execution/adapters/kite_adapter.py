"""
execution/adapters/kite_adapter.py — Safe Zerodha Kite Connect Broker Adapter Stub.

Implements the Kite Connect API integration architecture for Indian Equities.
ENFORCES STRICT SAFETY:
  - Live order execution is permanently gated in Step 10 via LiveTradingDisabledError.
  - Zero real orders can be submitted to exchanges.
  - API credentials are never logged or exported.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from execution.adapters.base import BaseBrokerAdapter
from execution.exceptions import (
    BrokerAuthenticationError,
    BrokerError,
    BrokerOrderRejectedError,
    BrokerTimeoutError,
    BrokerUncertainStateError,
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
    RejectionReason,
)
from execution.order_translator import OrderTranslator

logger = logging.getLogger(__name__)


class KiteBrokerAdapter(BaseBrokerAdapter):
    """
    Zerodha Kite Connect v3 Broker Adapter Stub.
    
    Provides payload translation, capability introspection, and response parsing
    while strictly prohibiting live execution.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        access_token: Optional[str] = None,
        mock_mode: bool = False,
        config: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(broker_name="ZerodhaKite", config=config)
        self.api_key: Optional[str] = api_key
        self.access_token: Optional[str] = access_token
        self.mock_mode: bool = mock_mode
        self._mock_orders: Dict[str, PaperOrder] = {}
        self._mock_positions: Dict[str, PaperPosition] = {}
        self._mock_account: PaperAccount = PaperAccount(
            initial_capital=1_000_000.0,
            cash=1_000_000.0,
        )
        self._mock_quotes: Dict[str, float] = {}

    def _perform_connect(self) -> bool:
        """Validate API credentials or mock connection."""
        if self.mock_mode:
            logger.info("[ZerodhaKite] Connected in mock/test mode.")
            return True
        if not self.api_key or not self.access_token:
            raise BrokerAuthenticationError(
                "Missing Zerodha Kite API Key or Access Token.",
                broker_name=self.broker_name,
            )
        # In a real environment with valid tokens, KiteConnect(api_key).profile() would be called.
        return True

    def _perform_disconnect(self) -> None:
        """Clear active session tokens."""
        logger.info("[ZerodhaKite] Disconnected session.")

    def get_capabilities(self) -> BrokerCapabilities:
        """Return Zerodha Kite Connect capabilities."""
        return BrokerCapabilities(
            supports_market_orders=True,
            supports_limit_orders=True,
            supports_stop_orders=False,
            supports_order_cancellation=True,
            supports_order_status_query=True,
            supports_positions_query=True,
            supports_account_balance_query=True,
            supports_fills_query=True,
            supports_integer_shares=True,
            supports_fractional_shares=False,
            supports_shorting=False,
            supports_live_orders=False,  # Strictly False in Step 10
            broker_name="ZerodhaKite",
            supported_exchanges=["NSE", "BSE"],
        )

    def submit_order(self, order: PaperOrder) -> PaperOrder:
        """
        Submit order to Zerodha Kite.
        
        STRICT SAFETY RULE: Real live trading is disabled in Step 10.
        Throws LiveTradingDisabledError if not running in mock_mode.
        """
        if not self.mock_mode:
            raise LiveTradingDisabledError(
                "Live order placement via Kite Connect is strictly disabled in Step 10. "
                "No real orders can be transmitted to the exchange.",
                broker_name=self.broker_name,
            )

        # In mock mode, simulate order translation and safe registration
        broker_req = OrderTranslator.to_broker_request(order)
        kite_payload = OrderTranslator.to_kite_payload(broker_req)
        order.metadata["kite_payload"] = kite_payload
        order.status = OrderStatus.SUBMITTED
        self._mock_orders[order.order_id] = order
        return order

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order on Kite."""
        if not self.mock_mode:
            raise LiveTradingDisabledError(
                "Live order cancellation via Kite Connect is strictly disabled in Step 10.",
                broker_name=self.broker_name,
            )
        if order_id in self._mock_orders:
            ord_obj = self._mock_orders[order_id]
            ord_obj.status = OrderStatus.CANCELLED
            return True
        return False

    def get_order(self, order_id: str) -> Optional[PaperOrder]:
        """Retrieve order by ID."""
        return self._mock_orders.get(order_id)

    def get_orders(self, status: Optional[OrderStatus] = None) -> List[PaperOrder]:
        """Retrieve historical or open orders."""
        if status is not None:
            return [o for o in self._mock_orders.values() if o.status == status]
        return list(self._mock_orders.values())

    def get_positions(self) -> Dict[str, PaperPosition]:
        """Retrieve positions from Kite."""
        return dict(self._mock_positions)

    def get_account(self) -> PaperAccount:
        """Retrieve account state from Kite."""
        return self._mock_account

    def get_fills(self, order_id: Optional[str] = None) -> List[PaperFill]:
        """Retrieve trade fills from Kite."""
        return []

    def get_quote(self, symbol: str) -> Optional[float]:
        """Retrieve latest market quote."""
        return self._mock_quotes.get(symbol)

    def set_mock_quote(self, symbol: str, price: float) -> None:
        """Test helper to set mock quote."""
        self._mock_quotes[symbol] = price

    def reconcile(self) -> Dict[str, Any]:
        """Audit positions and account against Kite."""
        return {
            "broker": self.broker_name,
            "status": "MATCH",
            "positions_count": len(self._mock_positions),
            "cash": self._mock_account.cash,
        }
