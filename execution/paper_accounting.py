"""
execution/paper_accounting.py — Robust Double-Entry Accounting Ledger for Paper Trading.

Maintains cash, positions, transaction history, realized/unrealized P&L, fees,
slippage, turnover, daily P&L, peak equity, and drawdown.

Strict Invariants:
  1. Integer shares only.
  2. Zero negative cash (Cash >= 0).
  3. Long-only cash equity (Shares >= 0, zero short positions).
  4. Zero leverage (Gross exposure <= Total Equity).
  5. Double-entry balance: Cash + sum(Market Values) == Total Equity.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Dict, List, Optional
from execution.models import (
    OrderSide,
    PaperAccount,
    PaperFill,
    PaperPosition,
    RejectionReason,
)


class PaperAccounting:
    """Double-entry accounting ledger managing cash and position balances."""

    def __init__(self, initial_capital: float = 1_000_000.0):
        self.initial_capital: float = float(initial_capital)
        self.account: PaperAccount = PaperAccount(
            initial_capital=self.initial_capital,
            cash=self.initial_capital,
            total_equity=self.initial_capital,
            peak_equity=self.initial_capital,
            start_of_day_equity=self.initial_capital,
        )
        self.positions: Dict[str, PaperPosition] = {}
        self.fills_history: List[PaperFill] = []

    def can_afford_buy(self, requested_shares: int, price: float, fee_rate: float) -> bool:
        """Check if cash balance can support purchase including fees."""
        if requested_shares <= 0 or price <= 0:
            return False
        total_cost = (requested_shares * price) * (1.0 + fee_rate)
        return self.account.cash >= total_cost

    def can_fulfill_sell(self, symbol: str, requested_shares: int) -> bool:
        """Check if account owns sufficient shares to execute sell."""
        if requested_shares <= 0:
            return False
        current_pos = self.positions.get(symbol)
        if current_pos is None or current_pos.shares < requested_shares:
            return False
        return True

    def apply_fill(self, fill: PaperFill) -> None:
        """
        Apply an executed fill to positions and cash balances.
        
        Guarantees integer share math, exact average cost basis updating,
        realized P&L computation, and cash debit/credit with fees.
        """
        if fill.quantity <= 0:
            return

        sym = fill.symbol
        qty = int(fill.quantity)
        px = float(fill.price)
        fee = float(fill.transaction_cost)
        slippage = float(fill.slippage)

        if fill.side == OrderSide.BUY:
            total_cost = (qty * px) + fee
            if total_cost > self.account.cash + 1e-6:
                raise ValueError(
                    f"Accounting invariant violated: Insufficient cash {self.account.cash:.2f} for buy cost {total_cost:.2f}"
                )

            # Debit cash
            self.account.cash = max(0.0, self.account.cash - total_cost)

            # Update or create position
            if sym in self.positions:
                pos = self.positions[sym]
                old_shares = pos.shares
                old_cost = pos.average_cost
                new_shares = old_shares + qty
                # Weighted average cost
                new_avg_cost = ((old_shares * old_cost) + (qty * px)) / new_shares
                pos.shares = new_shares
                pos.average_cost = new_avg_cost
                pos.recompute(px)
            else:
                self.positions[sym] = PaperPosition(
                    symbol=sym,
                    shares=qty,
                    average_cost=px,
                    current_price=px,
                )

            self.account.total_fees += fee
            self.account.total_slippage += slippage
            self.account.total_turnover += (qty * px)

        elif fill.side == OrderSide.SELL:
            if sym not in self.positions:
                raise ValueError(f"Accounting invariant violated: Attempted to sell unowned stock {sym}")

            pos = self.positions[sym]
            if pos.shares < qty:
                raise ValueError(
                    f"Accounting invariant violated: Attempted to sell {qty} shares but only own {pos.shares} of {sym}"
                )

            # Credit cash (notional minus fee)
            net_proceeds = (qty * px) - fee
            self.account.cash += net_proceeds

            # Calculate Realized P&L
            unit_gain = px - pos.average_cost
            trade_realized_pnl = (qty * unit_gain) - fee
            pos.realized_pnl += trade_realized_pnl
            self.account.realized_pnl += trade_realized_pnl

            # Reduce shares
            pos.shares -= qty
            if pos.shares == 0:
                del self.positions[sym]
            else:
                # Average cost remains unchanged on partial sales
                pos.recompute(px)

            self.account.total_fees += fee
            self.account.total_slippage += slippage
            self.account.total_turnover += (qty * px)

        self.fills_history.append(fill)
        self._recompute_totals()

    def mark_to_market(self, current_prices: Dict[str, float]) -> None:
        """Recompute current position market values, unrealized P&L, and equity."""
        for sym, pos in self.positions.items():
            if sym in current_prices and current_prices[sym] > 0:
                pos.recompute(current_prices[sym])
        self._recompute_totals()

    def _recompute_totals(self) -> None:
        """Internal double-entry recalculation."""
        pos_val = sum(p.market_value for p in self.positions.values())
        unrealized = sum(p.unrealized_pnl for p in self.positions.values())
        self.account.update_totals(positions_value=pos_val, unrealized_pnl=unrealized)

    def reset_daily_baseline(self) -> None:
        """Reset start-of-day equity baseline (e.g. at market open)."""
        self.account.start_of_day_equity = self.account.total_equity
        self.account.daily_pnl = 0.0

    def audit_invariants(self) -> Dict[str, bool]:
        """
        Verify long-only cash equity invariants.
        
        Returns dict of invariant name -> pass (True/False).
        """
        pos_val = sum(p.market_value for p in self.positions.values())
        equity_calc = self.account.cash + pos_val
        is_balance_exact = abs(equity_calc - self.account.total_equity) < 1e-4

        return {
            "no_negative_cash": self.account.cash >= -1e-6,
            "no_short_positions": all(p.shares >= 0 for p in self.positions.values()),
            "integer_shares": all(isinstance(p.shares, int) and p.shares == int(p.shares) for p in self.positions.values()),
            "no_leverage": (pos_val / self.account.total_equity <= 1.0001) if self.account.total_equity > 0 else True,
            "balance_identity": is_balance_exact,
        }
