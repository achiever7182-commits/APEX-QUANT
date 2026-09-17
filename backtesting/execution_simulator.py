"""
backtesting/execution_simulator.py — Realistic trade execution simulator.

Simulates order generation, price resolution according to configured execution convention,
slippage, transaction costs, liquidity participation caps, and whole-share integer fills.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple
import pandas as pd

from backtesting.models import HoldingPosition, OrderSide, OrderStatus, SimulatedFill, SimulatedOrder
from backtesting.data_feed import PointInTimeDataFeed
from portfolio.models import PortfolioBuildResult, PortfolioTarget


class ExecutionSimulator:
    """
    Simulates realistic order execution with transaction costs and slippage.
    """

    def __init__(
        self,
        execution_convention: str = "next_open",
        transaction_cost_bps: float = 10.0,
        slippage_bps: float = 5.0,
        liquidity_participation_limit: float = 0.05,
    ) -> None:
        """
        Parameters:
            execution_convention: 'next_open', 'next_close', or 'close_t'.
            transaction_cost_bps: Transaction cost in basis points (10 bps = 0.10%).
            slippage_bps: Slippage in basis points (5 bps = 0.05%).
            liquidity_participation_limit: Maximum fraction of volume for a single trade.
        """
        self.execution_convention = execution_convention
        self.transaction_cost_rate = transaction_cost_bps / 10_000.0
        self.slippage_rate = slippage_bps / 10_000.0
        self.liquidity_participation_limit = liquidity_participation_limit
        self._order_counter = 0

    def _next_order_id(self) -> str:
        self._order_counter += 1
        return f"ORD_{self._order_counter:06d}"

    def simulate_rebalance(
        self,
        signal_timestamp: pd.Timestamp,
        target_result: PortfolioBuildResult,
        current_holdings: Dict[str, HoldingPosition],
        current_cash: float,
        data_feed: PointInTimeDataFeed,
        total_equity: Optional[float] = None,
        max_single_stock_weight: float = 0.35,
        max_sector_weight: float = 0.55,
        sector_lookup: Optional[Dict[str, str]] = None,
    ) -> Tuple[List[SimulatedFill], float]:
        """
        Execute trades to transition current holdings to target portfolio.

        Orders are sequenced:
        1. SELL orders are executed first to release capital.
        2. BUY orders are executed second using available capital, enforcing post-execution constraints.

        Returns:
            Tuple of (List of SimulatedFill records, updated available cash).
        """
        fills: List[SimulatedFill] = []
        cash = current_cash

        eq = total_equity
        if eq is None:
            eq = current_cash + sum(p.shares * p.current_price for p in current_holdings.values())

        # Track sector values
        sec_lookup = sector_lookup or {}
        curr_sector_values: Dict[str, float] = {}
        for p in current_holdings.values():
            sec = sec_lookup.get(p.symbol, "Unknown")
            curr_sector_values[sec] = curr_sector_values.get(sec, 0.0) + (p.shares * p.current_price)

        # Determine target shares for all relevant symbols
        all_symbols = set(current_holdings.keys()).union(target_result.positions.keys())

        sell_diffs: List[Tuple[str, int]] = []
        buy_diffs: List[Tuple[str, int]] = []

        for sym in sorted(all_symbols):
            curr_shares = current_holdings[sym].shares if sym in current_holdings else 0
            tgt_pos = target_result.positions.get(sym)
            target_shares = tgt_pos.target_shares if tgt_pos is not None else 0

            delta = target_shares - curr_shares
            if delta < 0:
                sell_diffs.append((sym, abs(delta)))
            elif delta > 0:
                buy_diffs.append((sym, delta))

        # 1. Process SELL Orders
        for sym, req_shares in sell_diffs:
            curr_shares = current_holdings[sym].shares if sym in current_holdings else 0
            fill, cash_delta = self._execute_single_order(
                symbol=sym,
                side=OrderSide.SELL,
                requested_shares=req_shares,
                signal_timestamp=signal_timestamp,
                available_cash=cash,
                data_feed=data_feed,
                current_holding_shares=curr_shares,
                total_equity=eq,
            )
            if fill is not None:
                fills.append(fill)
                cash += cash_delta
                # Reduce sector value
                sec = sec_lookup.get(sym, "Unknown")
                curr_sector_values[sec] = max(0.0, curr_sector_values.get(sec, 0.0) - fill.notional)

        # 2. Process BUY Orders with Post-Execution Constraint Enforcement
        for sym, req_shares in buy_diffs:
            curr_shares = current_holdings[sym].shares if sym in current_holdings else 0
            fill, cash_delta = self._execute_single_order(
                symbol=sym,
                side=OrderSide.BUY,
                requested_shares=req_shares,
                signal_timestamp=signal_timestamp,
                available_cash=cash,
                data_feed=data_feed,
                current_holding_shares=curr_shares,
                total_equity=eq,
                max_single_stock_weight=max_single_stock_weight,
                max_sector_weight=max_sector_weight,
                current_sector_values=curr_sector_values,
                sector_lookup=sec_lookup,
            )
            if fill is not None:
                fills.append(fill)
                cash += cash_delta  # cash_delta is negative for buys
                # Increase sector value
                sec = sec_lookup.get(sym, "Unknown")
                curr_sector_values[sec] = curr_sector_values.get(sec, 0.0) + fill.notional

        return fills, cash

    def _execute_single_order(
        self,
        symbol: str,
        side: OrderSide,
        requested_shares: int,
        signal_timestamp: pd.Timestamp,
        available_cash: float,
        data_feed: PointInTimeDataFeed,
        current_holding_shares: int = 0,
        total_equity: Optional[float] = None,
        max_single_stock_weight: Optional[float] = None,
        max_sector_weight: Optional[float] = None,
        current_sector_values: Optional[Dict[str, float]] = None,
        sector_lookup: Optional[Dict[str, str]] = None,
    ) -> Tuple[Optional[SimulatedFill], float]:
        """Resolve price, pre-trade volume limits, slippage, and post-execution constraints."""
        if requested_shares <= 0:
            return None, 0.0

        # Determine execution bar based on convention
        exec_bar = None
        exec_time = signal_timestamp

        if self.execution_convention in ("next_open", "next_close"):
            next_bar = data_feed.get_next_bar(symbol, signal_timestamp)
            if next_bar is not None:
                exec_bar = next_bar
                exec_time = next_bar["timestamp"]
            else:
                exec_bar = data_feed.get_current_bar(symbol, signal_timestamp)
        else:  # 'close_t'
            exec_bar = data_feed.get_current_bar(symbol, signal_timestamp)

        if exec_bar is None:
            return None, 0.0

        # Base price lookup
        if self.execution_convention == "next_open" and "open" in exec_bar and pd.notna(exec_bar["open"]) and exec_bar["open"] > 0:
            base_price = float(exec_bar["open"])
        else:
            base_price = float(exec_bar["close"])

        # Calculate fill price with slippage
        if side == OrderSide.BUY:
            fill_price = base_price * (1.0 + self.slippage_rate)
        else:
            fill_price = base_price * (1.0 - self.slippage_rate)

        exec_shares = requested_shares
        status = OrderStatus.FILLED
        rej_reason = None

        # 1. Pre-Trade Historical Liquidity Limit (Zero Look-ahead into T+1 day's volume)
        # Uses 20-day rolling median volume strictly prior to execution bar (<= signal_timestamp)
        hist_dict = data_feed.get_bars_up_to(signal_timestamp)
        sym_hist = hist_dict.get(symbol)
        if sym_hist is not None and not sym_hist.empty and "volume" in sym_hist.columns:
            ref_volume = float(sym_hist["volume"].tail(20).median())
        elif "volume" in exec_bar and pd.notna(exec_bar["volume"]):
            ref_volume = float(exec_bar["volume"])
        else:
            ref_volume = 0.0

        if ref_volume > 0:
            max_liquidity_shares = int(math.floor(ref_volume * self.liquidity_participation_limit))
            if max_liquidity_shares < requested_shares:
                if max_liquidity_shares <= 0:
                    status = OrderStatus.REJECTED
                    rej_reason = "LIQUIDITY_LIMIT"
                    exec_shares = 0
                else:
                    exec_shares = max_liquidity_shares
                    status = OrderStatus.PARTIALLY_FILLED
                    rej_reason = "LIQUIDITY_LIMIT"

        # 2. Post-Execution Single-Stock Position Limit Check (prevents gap-induced violations)
        if side == OrderSide.BUY and exec_shares > 0 and total_equity is not None and total_equity > 0:
            max_stock_w = max_single_stock_weight or 0.35
            max_shares_allowed = int(math.floor((max_stock_w * total_equity) / fill_price))
            allowed_buy_shares = max(0, max_shares_allowed - current_holding_shares)
            if allowed_buy_shares < exec_shares:
                exec_shares = allowed_buy_shares
                if exec_shares == 0:
                    status = OrderStatus.REJECTED
                    rej_reason = "POSITION_LIMIT"
                else:
                    status = OrderStatus.PARTIALLY_FILLED
                    rej_reason = "POSITION_LIMIT"

            # 3. Post-Execution Sector Limit Check
            if max_sector_weight is not None and sector_lookup and symbol in sector_lookup and current_sector_values is not None:
                sec = sector_lookup[symbol]
                curr_sec_val = current_sector_values.get(sec, 0.0)
                max_sec_val = max_sector_weight * total_equity
                allowed_sec_val = max(0.0, max_sec_val - curr_sec_val)
                max_sec_shares = int(math.floor(allowed_sec_val / fill_price))
                if max_sec_shares < exec_shares:
                    exec_shares = max(0, max_sec_shares)
                    if exec_shares == 0:
                        status = OrderStatus.REJECTED
                        rej_reason = "SECTOR_LIMIT"
                    else:
                        status = OrderStatus.PARTIALLY_FILLED
                        rej_reason = "SECTOR_LIMIT"

        # 4. Cash constraint check for BUY orders
        if side == OrderSide.BUY and exec_shares > 0:
            per_share_cost = fill_price * (1.0 + self.transaction_cost_rate)
            max_affordable_shares = int(math.floor(available_cash / per_share_cost)) if per_share_cost > 0 else 0
            if max_affordable_shares < exec_shares:
                exec_shares = max(0, max_affordable_shares)
                if exec_shares == 0:
                    status = OrderStatus.REJECTED
                    rej_reason = "INSUFFICIENT_CASH"
                else:
                    status = OrderStatus.PARTIALLY_FILLED
                    rej_reason = "INSUFFICIENT_CASH"

        unfilled = requested_shares - exec_shares
        notional = exec_shares * fill_price
        fee = notional * self.transaction_cost_rate
        slippage_cost = abs(fill_price - base_price) * exec_shares
        total_cost = notional + fee if side == OrderSide.BUY else notional - fee

        cash_delta = - (notional + fee) if side == OrderSide.BUY else (notional - fee)

        fill = SimulatedFill(
            order_id=self._next_order_id(),
            timestamp=exec_time,
            symbol=symbol,
            side=side,
            requested_quantity=requested_shares,
            executed_quantity=exec_shares,
            unfilled_quantity=unfilled,
            execution_price=fill_price,
            notional=notional,
            slippage=slippage_cost,
            transaction_cost=fee,
            total_cost=total_cost,
            status=status,
            rejection_reason=rej_reason,
        )

        return fill, cash_delta

