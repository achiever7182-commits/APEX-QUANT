"""
backtesting/accounting.py — Exact portfolio ledger, mark-to-market accounting, and invariant auditor.

Maintains positions, average costs, realized and unrealized P&L, transaction costs,
and enforces double-entry balance identities with strict invariant audits.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence
import pandas as pd

from backtesting.models import HoldingPosition, OrderSide, PortfolioSnapshot, SimulatedFill
from data.corporate_actions.models import CorporateAction, CorporateActionType


class PortfolioAccounting:
    """
    Manages portfolio state, position tracking, cash balance, and accounting invariants.
    """

    def __init__(self, initial_capital: float = 1_000_000.0) -> None:
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions: Dict[str, HoldingPosition] = {}

        self.cumulative_realized_pnl: float = 0.0
        self.cumulative_fees: float = 0.0
        self.cumulative_slippage: float = 0.0
        self.cumulative_dividends: float = 0.0
        self.peak_value: float = initial_capital
        self.previous_equity: float = initial_capital

    @property
    def total_shares(self) -> int:
        return sum(pos.shares for pos in self.positions.values())

    def apply_corporate_actions(self, actions: Sequence[CorporateAction]) -> None:
        """
        Apply point-in-time corporate actions on their ex-date.

        Handles:
          - SPLIT: multiply shares by split_multiplier, divide average_cost by split_multiplier
          - BONUS: multiply shares by bonus multiplier, divide average_cost by bonus multiplier
          - DIVIDEND: credit cash by (shares * value), update cumulative_dividends
        """
        for action in actions:
            sym = action.symbol
            if sym not in self.positions:
                continue

            pos = self.positions[sym]
            if pos.shares <= 0:
                continue

            if action.action_type in (CorporateActionType.SPLIT, CorporateActionType.BONUS):
                mult = action.split_multiplier
                if mult > 0 and mult != 1.0:
                    old_shares = pos.shares
                    new_shares = int(math.floor(old_shares * mult))
                    if new_shares > 0:
                        old_cost = pos.average_cost
                        new_cost = (old_shares * old_cost) / new_shares
                        pos.shares = new_shares
                        pos.average_cost = new_cost
                        pos.market_value = new_shares * pos.current_price

            elif action.action_type == CorporateActionType.DIVIDEND:
                div_val = action.value
                if div_val > 0:
                    dividend_payout = pos.shares * div_val
                    self.cash += dividend_payout
                    self.cumulative_dividends += dividend_payout


    def apply_fills(self, fills: List[SimulatedFill]) -> None:
        """
        Update position ledger and cash balances from executed fills.

        Average cost basis is used for stock purchases and realized P&L on sales.
        """
        for fill in fills:
            if fill.executed_quantity <= 0:
                continue

            sym = fill.symbol
            qty = fill.executed_quantity
            px = fill.execution_price
            notional = fill.notional
            fee = fill.transaction_cost
            slip = fill.slippage

            self.cumulative_fees += fee
            self.cumulative_slippage += slip

            if fill.side == OrderSide.BUY:
                self.cash -= (notional + fee)
                if sym not in self.positions:
                    self.positions[sym] = HoldingPosition(
                        symbol=sym,
                        shares=qty,
                        average_cost=px,
                        current_price=px,
                        market_value=notional,
                        weight=0.0,
                        unrealized_pnl=0.0,
                    )
                else:
                    curr_pos = self.positions[sym]
                    total_shares = curr_pos.shares + qty
                    new_cost = ((curr_pos.shares * curr_pos.average_cost) + notional) / total_shares if total_shares > 0 else 0.0
                    curr_pos.shares = total_shares
                    curr_pos.average_cost = new_cost
                    curr_pos.current_price = px
                    curr_pos.market_value = total_shares * px

            elif fill.side == OrderSide.SELL:
                self.cash += (notional - fee)
                if sym in self.positions:
                    curr_pos = self.positions[sym]
                    # Realized P&L on the sold portion
                    gross_pnl = (px - curr_pos.average_cost) * qty
                    net_pnl = gross_pnl - fee
                    self.cumulative_realized_pnl += net_pnl

                    curr_pos.shares -= qty
                    if curr_pos.shares <= 0:
                        del self.positions[sym]
                    else:
                        curr_pos.current_price = px
                        curr_pos.market_value = curr_pos.shares * px

    def mark_to_market(
        self,
        timestamp: pd.Timestamp,
        current_prices: Dict[str, float],
        sector_map: Optional[Dict[str, str]] = None,
        is_rebalance_bar: bool = False,
        rebalance_turnover: float = 0.0,
    ) -> PortfolioSnapshot:
        """
        Evaluate current portfolio value, position weights, unrealized P&L, and returns.

        Parameters:
            timestamp: Simulation timestamp.
            current_prices: Map of symbol -> current closing price.
            sector_map: Optional map of symbol -> sector name.
            is_rebalance_bar: Flag indicating if a rebalance occurred on this bar.
            rebalance_turnover: Turnover fraction executed on this bar.

        Returns:
            Strongly typed PortfolioSnapshot.
        """
        total_pos_value = 0.0
        total_unrealized_pnl = 0.0

        for sym, pos in list(self.positions.items()):
            if sym in current_prices and current_prices[sym] > 0:
                pos.current_price = float(current_prices[sym])
            pos.market_value = pos.shares * pos.current_price
            pos.unrealized_pnl = (pos.current_price - pos.average_cost) * pos.shares
            if sector_map and sym in sector_map:
                pos.sector = sector_map[sym]
            total_pos_value += pos.market_value
            total_unrealized_pnl += pos.unrealized_pnl

        portfolio_value = self.cash + total_pos_value

        # Update position weights
        for pos in self.positions.values():
            pos.weight = pos.market_value / portfolio_value if portfolio_value > 0 else 0.0

        gross_exp = total_pos_value / portfolio_value if portfolio_value > 0 else 0.0
        daily_ret = (portfolio_value - self.previous_equity) / self.previous_equity if self.previous_equity > 0 else 0.0
        self.previous_equity = portfolio_value

        cum_ret = (portfolio_value - self.initial_capital) / self.initial_capital if self.initial_capital > 0 else 0.0
        if portfolio_value > self.peak_value:
            self.peak_value = portfolio_value

        dd = (self.peak_value - portfolio_value) / self.peak_value if self.peak_value > 0 else 0.0

        # Enforce accounting invariants
        self._audit_invariants(portfolio_value, total_pos_value)

        # Clone positions dictionary for historical snapshot
        positions_clone = {
            s: HoldingPosition(
                symbol=p.symbol,
                shares=p.shares,
                average_cost=p.average_cost,
                current_price=p.current_price,
                market_value=p.market_value,
                weight=p.weight,
                unrealized_pnl=p.unrealized_pnl,
                sector=p.sector,
            )
            for s, p in self.positions.items()
        }

        return PortfolioSnapshot(
            timestamp=timestamp,
            cash=self.cash,
            positions=positions_clone,
            gross_exposure=gross_exp,
            portfolio_value=portfolio_value,
            daily_return=daily_ret,
            cumulative_return=cum_ret,
            peak_value=self.peak_value,
            drawdown=dd,
            realized_pnl=self.cumulative_realized_pnl,
            unrealized_pnl=total_unrealized_pnl,
            fees_paid=self.cumulative_fees,
            slippage_paid=self.cumulative_slippage,
            turnover=rebalance_turnover,
            is_rebalance_bar=is_rebalance_bar,
        )

    def _audit_invariants(self, portfolio_value: float, total_pos_value: float) -> None:
        """Enforce strict accounting identities and non-negativity."""
        if self.cash < -1e-4:
            raise ValueError(f"Accounting Invariant Violation: Negative cash balance (₹{self.cash:.2f})")

        identity_diff = abs((self.cash + total_pos_value) - portfolio_value)
        if identity_diff > 1e-4:
            raise ValueError(f"Accounting Invariant Violation: Identity mismatch (Cash + Pos != Equity, diff: {identity_diff:.6f})")

        for s, p in self.positions.items():
            if p.shares < 0:
                raise ValueError(f"Accounting Invariant Violation: Negative shares for {s} ({p.shares})")
            if not isinstance(p.shares, int):
                raise ValueError(f"Accounting Invariant Violation: Fractional shares for {s} ({p.shares})")
