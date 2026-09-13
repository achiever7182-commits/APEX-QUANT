"""
core/execution.py — Smart order executor with limit-order support and fee tracking.

Instead of always firing market orders, tries a limit order at a better price
first. If it doesn't fill within the timeout, falls back to a market order.
Tracks all fees paid so P&L calculations are accurate.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from config import EXECUTION_MODE, LIMIT_ORDER_TIMEOUT_SECONDS


@dataclass
class FillResult:
    """The result of an order execution."""
    side: str          # 'buy' or 'sell'
    fill_price: float
    filled_qty: float
    fee_paid: float    # in quote currency (USDT)
    order_id: str
    method: str        # 'limit' or 'market'


@dataclass
class FeeTracker:
    """Accumulates all fees paid during a session."""
    total_fees: float = 0.0
    trade_count: int = 0

    def record(self, fee: float) -> None:
        self.total_fees += fee
        self.trade_count += 1

    @property
    def average_fee(self) -> float:
        return self.total_fees / self.trade_count if self.trade_count else 0.0


# Module-level fee tracker shared across the session
fee_tracker = FeeTracker()


def execute_order(
    adapter,
    side: str,
    amount: float,
    current_price: float,
    *,
    limit_offset_pct: float = 0.01,
) -> FillResult:
    """
    Execute a buy or sell order using the configured execution mode.

    In 'limit' mode:
        Places a limit order slightly inside the spread and waits up to
        LIMIT_ORDER_TIMEOUT_SECONDS for a fill. Falls back to market if needed.

    In 'market' mode:
        Always fires a market order immediately.

    Args:
        adapter          — BinanceTestnetAdapter instance
        side             — 'buy' or 'sell'
        amount           — quantity to buy/sell
        current_price    — latest market price (used for limit price calculation)
        limit_offset_pct — how much better than market to set the limit price (%)

    Returns:
        FillResult with fill details and fees.
    """
    if EXECUTION_MODE == "limit":
        return _try_limit_with_fallback(adapter, side, amount, current_price, limit_offset_pct)
    return _market_order(adapter, side, amount, current_price)


def _limit_price(side: str, price: float, offset_pct: float) -> float:
    """
    Calculate a limit price that is slightly better than market.
    For buys: slightly below market (we pay less).
    For sells: slightly above market (we receive more).
    """
    factor = 1.0 - offset_pct / 100.0 if side == "buy" else 1.0 + offset_pct / 100.0
    return round(price * factor, 2)


def _extract_fill(order: dict[str, Any], fallback_price: float) -> tuple[float, float, float]:
    """Extract (fill_price, filled_qty, fee) from a CCXT order dict."""
    average = order.get("average") or order.get("price")
    fill_price = float(average) if average else fallback_price
    filled_qty = float(order.get("filled") or 0.0)
    # CCXT sometimes exposes fees; estimate from cost if not available
    fee_info = order.get("fee") or {}
    fee = float(fee_info.get("cost") or 0.0)
    if fee == 0.0 and filled_qty > 0:
        # Default Binance taker fee: 0.1%
        fee = fill_price * filled_qty * 0.001
    return fill_price, filled_qty, fee


def _market_order(adapter, side: str, amount: float, current_price: float) -> FillResult:
    order = adapter.place_market_order(side, amount)
    fill_price, filled_qty, fee = _extract_fill(order, current_price)
    fee_tracker.record(fee)
    return FillResult(
        side=side,
        fill_price=fill_price,
        filled_qty=filled_qty,
        fee_paid=fee,
        order_id=str(order.get("id", "n/a")),
        method="market",
    )


def _try_limit_with_fallback(
    adapter,
    side: str,
    amount: float,
    current_price: float,
    offset_pct: float,
) -> FillResult:
    lp = _limit_price(side, current_price, offset_pct)
    try:
        order = adapter.place_limit_order(side, amount, lp)
        order_id = str(order.get("id", "n/a"))
        deadline = time.monotonic() + LIMIT_ORDER_TIMEOUT_SECONDS

        while time.monotonic() < deadline:
            time.sleep(0.5)
            refreshed = adapter.fetch_order(order_id)
            status = refreshed.get("status", "")
            if status == "closed":
                fill_price, filled_qty, fee = _extract_fill(refreshed, lp)
                fee_tracker.record(fee)
                return FillResult(
                    side=side,
                    fill_price=fill_price,
                    filled_qty=filled_qty,
                    fee_paid=fee,
                    order_id=order_id,
                    method="limit",
                )

        # Timeout — cancel limit and check for partial fills before falling back
        try:
            adapter.cancel_order(order_id)
        except Exception:
            pass

        # Fetch final order status to see if any partial quantity filled
        try:
            refreshed = adapter.fetch_order(order_id)
            limit_fill_price, limit_filled_qty, limit_fee = _extract_fill(refreshed, lp)
        except Exception:
            limit_fill_price, limit_filled_qty, limit_fee = lp, 0.0, 0.0

        if limit_filled_qty >= amount:
            # Order fully filled just as cancel was sent
            fee_tracker.record(limit_fee)
            return FillResult(
                side=side,
                fill_price=limit_fill_price,
                filled_qty=limit_filled_qty,
                fee_paid=limit_fee,
                order_id=order_id,
                method="limit",
            )

        remaining_qty = amount - limit_filled_qty
        if limit_filled_qty > 0:
            print(
                f"[execution] Limit order partially filled: {limit_filled_qty:.6f}/{amount:.6f} @ {limit_fill_price:.2f}. "
                f"Placing market order for remaining {remaining_qty:.6f}"
            )
            fee_tracker.record(limit_fee)
            # If remaining quantity is too small for Binance min notional (~0.00001 BTC), return the partial fill
            if remaining_qty <= 0.00001:
                return FillResult(
                    side=side,
                    fill_price=limit_fill_price,
                    filled_qty=limit_filled_qty,
                    fee_paid=limit_fee,
                    order_id=order_id,
                    method="limit",
                )
            market_res = _market_order(adapter, side, remaining_qty, current_price)
            total_qty = limit_filled_qty + market_res.filled_qty
            total_cost = (limit_fill_price * limit_filled_qty) + (market_res.fill_price * market_res.filled_qty)
            combined_fill_price = total_cost / total_qty if total_qty > 0 else current_price
            combined_fee = limit_fee + market_res.fee_paid
            return FillResult(
                side=side,
                fill_price=combined_fill_price,
                filled_qty=total_qty,
                fee_paid=combined_fee,
                order_id=f"{order_id}+{market_res.order_id}",
                method="limit+market",
            )

        print(f"[execution] Limit order timed out with 0 fills — falling back to market order")
        return _market_order(adapter, side, amount, current_price)

    except Exception as e:
        print(f"[execution] Limit order failed ({e}) — falling back to market order")
        return _market_order(adapter, side, amount, current_price)
