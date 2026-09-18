"""
execution/order_translator.py — Broker-Neutral Order Translation Layer.

Translates internal domain models (PaperOrder) into normalized broker requests
(BrokerOrderRequest) and vendor-specific payloads (e.g., Zerodha Kite Connect, Upstox).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from execution.models import OrderSide, OrderStatus, OrderType, PaperOrder


@dataclass
class BrokerOrderRequest:
    """Standardized broker-neutral order request."""
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: int
    exchange: str = "NSE"
    product: str = "CNC"  # Cash-n-Carry (standard for equity delivery)
    validity: str = "DAY"
    limit_price: Optional[float] = None
    trigger_price: Optional[float] = None
    client_order_id: Optional[str] = None
    tag: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "exchange": self.exchange,
            "side": self.side.value if isinstance(self.side, OrderSide) else str(self.side),
            "order_type": self.order_type.value if isinstance(self.order_type, OrderType) else str(self.order_type),
            "quantity": self.quantity,
            "product": self.product,
            "validity": self.validity,
            "limit_price": self.limit_price,
            "trigger_price": self.trigger_price,
            "client_order_id": self.client_order_id,
            "tag": self.tag,
            "metadata": self.metadata,
        }


class OrderTranslator:
    """
    Translates between APEX internal order models and external broker formats.
    """

    @staticmethod
    def to_broker_request(
        order: PaperOrder,
        exchange: str = "NSE",
        product: str = "CNC",
        validity: str = "DAY",
        tag: Optional[str] = None,
    ) -> BrokerOrderRequest:
        """
        Convert an internal PaperOrder into a normalized BrokerOrderRequest.
        """
        return BrokerOrderRequest(
            symbol=order.symbol,
            side=order.side,
            order_type=order.order_type,
            quantity=order.requested_quantity,
            exchange=exchange,
            product=product,
            validity=validity,
            limit_price=order.limit_price,
            client_order_id=order.order_id,
            tag=tag or (order.order_id[:8] if order.order_id else None),
            metadata=dict(order.metadata),
        )

    @staticmethod
    def to_kite_payload(request: BrokerOrderRequest) -> Dict[str, Any]:
        """
        Convert a BrokerOrderRequest to Zerodha Kite Connect order placement payload.
        
        Ref: https://kite.trade/docs/connect/v3/orders/#placing-orders
        """
        transaction_type = "BUY" if request.side == OrderSide.BUY else "SELL"
        order_type_str = "MARKET" if request.order_type == OrderType.MARKET else "LIMIT"
        
        payload: Dict[str, Any] = {
            "variety": "regular",
            "exchange": request.exchange,
            "tradingsymbol": request.symbol,
            "transaction_type": transaction_type,
            "quantity": int(request.quantity),
            "product": request.product,
            "order_type": order_type_str,
            "validity": request.validity,
        }

        if request.order_type == OrderType.LIMIT and request.limit_price is not None:
            payload["price"] = round(float(request.limit_price), 2)

        if request.trigger_price is not None:
            payload["trigger_price"] = round(float(request.trigger_price), 2)

        if request.tag:
            # Kite limits tag to 8 alphanumeric characters
            clean_tag = "".join(c for c in request.tag if c.isalnum())[:8]
            if clean_tag:
                payload["tag"] = clean_tag

        return payload

    @staticmethod
    def parse_kite_status(kite_status: str) -> OrderStatus:
        """Map Zerodha Kite order status string to internal OrderStatus enum."""
        mapping = {
            "COMPLETE": OrderStatus.FILLED,
            "REJECTED": OrderStatus.REJECTED,
            "CANCELLED": OrderStatus.CANCELLED,
            "OPEN": OrderStatus.SUBMITTED,
            "TRIGGER PENDING": OrderStatus.SUBMITTED,
            "PUT ORDER REQ RECEIVED": OrderStatus.SUBMITTED,
            "VALIDATION PENDING": OrderStatus.VALIDATED,
        }
        return mapping.get(kite_status.upper(), OrderStatus.SUBMITTED)
