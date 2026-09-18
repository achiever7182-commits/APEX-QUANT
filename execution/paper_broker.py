"""
execution/paper_broker.py — Realistic Paper Execution Broker for APEX QUANT.

Implements the Broker interface for Indian Equities. Simulates realistic order
execution using latest market quotes, slippage, brokerage fees, integer shares,
and liquidity participation caps.
"""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from execution.broker import Broker
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
from execution.paper_accounting import PaperAccounting
from execution.reconciliation import ReconciliationEngine




class PaperBroker(Broker):
    """
    Production-grade Paper Trading Broker.

    Simulates execution with explicit lifecycle states, fees, slippage, and
    double-entry accounting updates.
    """

    def __init__(
        self,
        initial_capital: float = 1_000_000.0,
        transaction_cost_bps: float = 10.0,
        slippage_bps: float = 5.0,
        liquidity_participation_limit: float = 0.05,
    ):
        self.transaction_cost_rate: float = transaction_cost_bps / 10_000.0
        self.slippage_rate: float = slippage_bps / 10_000.0
        self.liquidity_participation_limit: float = liquidity_participation_limit

        self.accounting: PaperAccounting = PaperAccounting(initial_capital=initial_capital)
        self.orders: Dict[str, PaperOrder] = {}
        self.fills: List[PaperFill] = []
        self.market_prices: Dict[str, float] = {}
        self.market_volumes: Dict[str, float] = {}

    def update_market_price(self, symbol: str, price: float, volume: Optional[float] = None) -> None:
        """Update current market quote for an asset and mark portfolio to market."""
        if price > 0:
            self.market_prices[symbol] = float(price)
            if volume is not None and volume >= 0:
                self.market_volumes[symbol] = float(volume)
            self.accounting.mark_to_market(self.market_prices)

    def update_market_panel(self, quotes: Dict[str, float], volumes: Optional[Dict[str, float]] = None) -> None:
        """Update quotes across universe."""
        for sym, px in quotes.items():
            if px > 0:
                self.market_prices[sym] = float(px)
        if volumes:
            for sym, vol in volumes.items():
                if vol >= 0:
                    self.market_volumes[sym] = float(vol)
        self.accounting.mark_to_market(self.market_prices)

    def submit_order(self, order: PaperOrder) -> PaperOrder:
        """
        Submit a paper order for validation and execution.
        
        Lifecycle: CREATED -> VALIDATED -> (ACCEPTED | REJECTED) -> (PARTIALLY_FILLED | FILLED)
        """
        order.validated_at = datetime.now(timezone.utc).isoformat()
        self.orders[order.order_id] = order

        # 1. Basic validation
        if order.requested_quantity <= 0 or not isinstance(order.requested_quantity, int):
            order.status = OrderStatus.REJECTED
            order.rejection_reason = RejectionReason.INVALID_ORDER
            order.rejection_details = f"Quantity must be a positive integer, got {order.requested_quantity}"
            order.completed_at = datetime.now(timezone.utc).isoformat()
            return order

        sym = order.symbol
        base_price = self.market_prices.get(sym)
        if base_price is None or base_price <= 0:
            order.status = OrderStatus.REJECTED
            order.rejection_reason = RejectionReason.STALE_DATA
            order.rejection_details = f"No current market price available for {sym}"
            order.completed_at = datetime.now(timezone.utc).isoformat()
            return order

        # 2. Pre-execution checks based on side
        if order.side == OrderSide.BUY:
            # Check if at least 1 share can be afforded at base price + fees
            per_share_cost = base_price * (1.0 + self.slippage_rate) * (1.0 + self.transaction_cost_rate)
            if self.accounting.account.cash < per_share_cost:
                order.status = OrderStatus.REJECTED
                order.rejection_reason = RejectionReason.INSUFFICIENT_CASH
                order.rejection_details = (
                    f"Cash {self.accounting.account.cash:.2f} insufficient for 1 share at {per_share_cost:.2f}"
                )
                order.completed_at = datetime.now(timezone.utc).isoformat()
                return order

        elif order.side == OrderSide.SELL:
            current_pos = self.accounting.positions.get(sym)
            if current_pos is None or current_pos.shares <= 0:
                order.status = OrderStatus.REJECTED
                order.rejection_reason = RejectionReason.INSUFFICIENT_SHARES
                order.rejection_details = f"Zero shares owned for {sym}"
                order.completed_at = datetime.now(timezone.utc).isoformat()
                return order
            if current_pos.shares < order.requested_quantity:
                order.status = OrderStatus.REJECTED
                order.rejection_reason = RejectionReason.INSUFFICIENT_SHARES
                order.rejection_details = (
                    f"Requested sell {order.requested_quantity} exceeds owned {current_pos.shares} shares"
                )
                order.completed_at = datetime.now(timezone.utc).isoformat()
                return order

        order.status = OrderStatus.ACCEPTED
        order.submitted_at = datetime.now(timezone.utc).isoformat()

        # 3. Simulate execution fill
        exec_shares = order.requested_quantity

        # Liquidity constraint: partial fill if order exceeds liquidity cap
        ref_vol = self.market_volumes.get(sym)
        if ref_vol is not None and ref_vol > 0 and self.liquidity_participation_limit > 0:
            max_liquidity_shares = int(math.floor(ref_vol * self.liquidity_participation_limit))
            if max_liquidity_shares < exec_shares:
                exec_shares = max(0, max_liquidity_shares)

        # Cash constraint on BUY orders (calculate exact affordable shares)
        slip_direction = 1.0 if order.side == OrderSide.BUY else -1.0
        fill_price = base_price * (1.0 + slip_direction * self.slippage_rate)

        if order.side == OrderSide.BUY:
            per_share_fill_cost = fill_price * (1.0 + self.transaction_cost_rate)
            max_cash_shares = int(math.floor(self.accounting.account.cash / per_share_fill_cost)) if per_share_fill_cost > 0 else 0
            if max_cash_shares < exec_shares:
                exec_shares = max(0, max_cash_shares)

        if exec_shares <= 0:
            order.status = OrderStatus.REJECTED
            order.rejection_reason = (
                RejectionReason.INSUFFICIENT_CASH if order.side == OrderSide.BUY else RejectionReason.LIQUIDITY_LIMIT
            )
            order.rejection_details = "Zero shares executable after cash/liquidity sizing"
            order.completed_at = datetime.now(timezone.utc).isoformat()
            return order

        # 4. Generate Fill
        notional = exec_shares * fill_price
        fee = notional * self.transaction_cost_rate
        slippage_cost = abs(fill_price - base_price) * exec_shares

        fill = PaperFill(
            fill_id=f"FILL-{uuid.uuid4().hex[:12].upper()}",
            order_id=order.order_id,
            symbol=sym,
            side=order.side,
            quantity=exec_shares,
            price=fill_price,
            slippage=slippage_cost,
            transaction_cost=fee,
            total_notional=notional,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        # 5. Apply fill to accounting ledger
        self.accounting.apply_fill(fill)
        self.fills.append(fill)

        # 6. Update order state
        order.filled_quantity = exec_shares
        order.unfilled_quantity = order.requested_quantity - exec_shares
        order.average_fill_price = fill_price
        order.completed_at = datetime.now(timezone.utc).isoformat()

        if exec_shares == order.requested_quantity:
            order.status = OrderStatus.FILLED
        else:
            order.status = OrderStatus.PARTIALLY_FILLED
            order.rejection_reason = RejectionReason.LIQUIDITY_LIMIT

        return order

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an unfilled or partially filled order."""
        if order_id not in self.orders:
            return False
        ord_obj = self.orders[order_id]
        if ord_obj.status in (OrderStatus.CREATED, OrderStatus.VALIDATED, OrderStatus.ACCEPTED):
            ord_obj.status = OrderStatus.CANCELLED
            ord_obj.completed_at = datetime.now(timezone.utc).isoformat()
            return True
        return False

    def get_order(self, order_id: str) -> Optional[PaperOrder]:
        return self.orders.get(order_id)

    def get_positions(self) -> Dict[str, PaperPosition]:
        return dict(self.accounting.positions)

    def get_account(self) -> PaperAccount:
        return self.accounting.account

    def get_fills(self, order_id: Optional[str] = None) -> List[PaperFill]:
        if order_id:
            return [f for f in self.fills if f.order_id == order_id]
        return list(self.fills)

    def get_orders(self, status: Optional[OrderStatus] = None) -> List[PaperOrder]:
        """Retrieve historical or open orders, optionally filtered by status."""
        if status is not None:
            return [o for o in self.orders.values() if o.status == status]
        return list(self.orders.values())

    def get_quote(self, symbol: str) -> Optional[float]:
        """Retrieve the latest market quote for a symbol."""
        return self.market_prices.get(symbol)

    def reconcile(self) -> Dict[str, Any]:
        """Audit and compare broker internal accounting and positions."""
        report = ReconciliationEngine.reconcile(
            account=self.accounting.account,
            positions=self.accounting.positions,
            fills=self.fills,
        )
        return report.to_dict()


    def get_capabilities(self) -> BrokerCapabilities:
        """Return the explicit capability matrix supported by PaperBroker."""
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
            supports_live_orders=False,
            broker_name="PaperBroker",
            supported_exchanges=["NSE"],
        )

    def get_connection_status(self) -> BrokerConnectionState:
        """Return the current connection status."""
        return BrokerConnectionState.CONNECTED

