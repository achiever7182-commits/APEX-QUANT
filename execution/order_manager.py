"""
execution/order_manager.py — Order Lifecycle & Routing Manager for Paper Trading.

Manages the explicit order state machine:
  CREATED -> VALIDATED -> ACCEPTED / REJECTED -> PARTIALLY_FILLED -> FILLED / CANCELLED

Coordinates pre-trade risk evaluation, order submission to PaperBroker,
event logging, and in-flight order registry.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Callable, Dict, List, Optional
from execution.broker import Broker
from execution.data_adapter import ValidatedQuote
from execution.exceptions import (
    BrokerError,
    BrokerOrderRejectedError,
    BrokerTimeoutError,
    BrokerUncertainStateError,
)
from execution.models import (
    OrderStatus,
    PaperAuditEvent,
    PaperOrder,
    RejectionReason,
)

if TYPE_CHECKING:
    from risk.paper_risk_manager import PaperRiskManager



class OrderManager:
    """Coordinates order creation, risk gatekeeping, routing, and lifecycle state tracking."""

    def __init__(
        self,
        broker: Broker,
        risk_manager: PaperRiskManager,
        event_callback: Optional[Callable[[PaperAuditEvent], None]] = None,
    ):
        self.broker: Broker = broker
        self.risk_manager: PaperRiskManager = risk_manager
        self.event_callback: Optional[Callable[[PaperAuditEvent], None]] = event_callback
        self.orders: Dict[str, PaperOrder] = {}

    def _emit_event(self, event_type: str, payload: Dict[str, any], level: str = "INFO") -> None:
        event = PaperAuditEvent(event_type=event_type, payload=payload, level=level)
        if self.event_callback:
            self.event_callback(event)

    def submit_order(
        self,
        order: PaperOrder,
        quote: ValidatedQuote,
        reference_volume: Optional[float] = None,
        as_of_time: Optional[any] = None,
    ) -> PaperOrder:
        """
        Drive order through validation, risk evaluation, and broker submission.
        """
        self.orders[order.order_id] = order
        order.validated_at = datetime.now(timezone.utc).isoformat()
        order.status = OrderStatus.VALIDATED

        self._emit_event(
            "ORDER_CREATED",
            {
                "order_id": order.order_id,
                "symbol": order.symbol,
                "side": order.side.value,
                "quantity": order.requested_quantity,
                "idempotency_key": order.idempotency_key,
            },
        )

        # 1. Pre-Trade Risk Checks
        account = self.broker.get_account()
        positions = self.broker.get_positions()
        risk_result = self.risk_manager.evaluate_order(
            order=order,
            account=account,
            positions=positions,
            quote=quote,
            reference_volume=reference_volume,
            as_of_time=as_of_time,
        )

        if not risk_result.passed:
            order.status = OrderStatus.REJECTED
            order.rejection_reason = risk_result.rejection_reason
            order.rejection_details = risk_result.details
            order.completed_at = datetime.now(timezone.utc).isoformat()

            self._emit_event(
                "RISK_REJECTED",
                {
                    "order_id": order.order_id,
                    "symbol": order.symbol,
                    "reason": risk_result.rejection_reason.value if risk_result.rejection_reason else "UNKNOWN",
                    "details": risk_result.details,
                },
                level="WARNING",
            )
            return order

        # 2. Submit to Broker
        try:
            executed_order = self.broker.submit_order(order)
            self.orders[order.order_id] = executed_order
        except (BrokerTimeoutError, BrokerUncertainStateError) as e:
            # FAIL-CLOSED SAFETY: State at broker is ambiguous.
            # Mark order as SUBMITTED (in-flight) and NEVER retry blindly.
            order.status = OrderStatus.SUBMITTED
            order.metadata["uncertain_state"] = True
            order.metadata["error"] = str(e)
            order.rejection_details = f"Broker timeout/uncertain state: {str(e)}. Awaiting reconciliation. DO NOT RETRY."
            self.orders[order.order_id] = order
            self._emit_event(
                "ORDER_TIMEOUT_UNCERTAIN",
                {
                    "order_id": order.order_id,
                    "symbol": order.symbol,
                    "error": str(e),
                },
                level="CRITICAL",
            )
            return order
        except BrokerOrderRejectedError as e:
            order.status = OrderStatus.REJECTED
            order.rejection_reason = RejectionReason.BROKER_ERROR
            order.rejection_details = str(e)
            order.completed_at = datetime.now(timezone.utc).isoformat()
            self.orders[order.order_id] = order
            self._emit_event(
                "ORDER_REJECTED",
                {
                    "order_id": order.order_id,
                    "symbol": order.symbol,
                    "reason": "BROKER_REJECTED",
                    "details": str(e),
                },
                level="ERROR",
            )
            return order
        except Exception as e:
            order.status = OrderStatus.REJECTED
            order.rejection_reason = RejectionReason.BROKER_ERROR
            order.rejection_details = f"Unexpected broker error: {str(e)}"
            order.completed_at = datetime.now(timezone.utc).isoformat()
            self.orders[order.order_id] = order
            self._emit_event(
                "ORDER_REJECTED",
                {
                    "order_id": order.order_id,
                    "symbol": order.symbol,
                    "reason": "BROKER_ERROR",
                    "details": str(e),
                },
                level="ERROR",
            )
            return order

        # 3. Emit fill/status event
        if executed_order.status == OrderStatus.FILLED:
            self._emit_event(
                "ORDER_FILLED",
                {
                    "order_id": order.order_id,
                    "symbol": order.symbol,
                    "quantity": order.filled_quantity,
                    "avg_price": order.average_fill_price,
                },
            )
        elif executed_order.status == OrderStatus.PARTIALLY_FILLED:
            self._emit_event(
                "ORDER_PARTIALLY_FILLED",
                {
                    "order_id": order.order_id,
                    "symbol": order.symbol,
                    "filled_quantity": order.filled_quantity,
                    "unfilled_quantity": order.unfilled_quantity,
                    "avg_price": order.average_fill_price,
                    "reason": order.rejection_reason.value if order.rejection_reason else "PARTIAL",
                },
                level="WARNING",
            )
        elif executed_order.status == OrderStatus.REJECTED:
            self._emit_event(
                "ORDER_REJECTED",
                {
                    "order_id": order.order_id,
                    "symbol": order.symbol,
                    "reason": order.rejection_reason.value if order.rejection_reason else "UNKNOWN",
                    "details": order.rejection_details,
                },
                level="ERROR",
            )

        return executed_order

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order via broker."""
        res = self.broker.cancel_order(order_id)
        if res:
            self._emit_event("ORDER_CANCELLED", {"order_id": order_id})
        return res

    def get_order(self, order_id: str) -> Optional[PaperOrder]:
        return self.orders.get(order_id)

    def get_active_orders(self) -> List[PaperOrder]:
        return [
            o for o in self.orders.values()
            if o.status in (OrderStatus.CREATED, OrderStatus.VALIDATED, OrderStatus.SUBMITTED, OrderStatus.ACCEPTED)
        ]

