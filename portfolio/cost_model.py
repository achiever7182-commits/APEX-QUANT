"""
portfolio/cost_model.py — Transaction Cost and Turnover Model.

Models:
  - One-way portfolio turnover between current and target allocations
  - Estimated trading commission and market impact/slippage in basis points
  - Rebalance dollar volume

DISCLAIMER: These cost calculations are research approximations for strategy
evaluation. They do not constitute exact execution fee schedules for Indian brokers.
"""

from __future__ import annotations

from typing import Dict, Tuple
from portfolio.models import PortfolioPosition, PortfolioTarget


class TransactionCostModel:
    """
    Computes rebalancing turnover and estimated transaction execution costs.
    """

    @staticmethod
    def compute_turnover(
        current_weights: Dict[str, float],
        target_weights: Dict[str, float],
    ) -> float:
        """
        Compute one-way portfolio turnover: 0.5 * sum(|w_target - w_current|).

        Parameters:
            current_weights: Mapping of symbol -> current weight (excluding cash).
            target_weights: Mapping of symbol -> target weight (excluding cash).

        Returns:
            One-way turnover fraction in [0.0, 1.0].
        """
        all_symbols = set(current_weights.keys()).union(set(target_weights.keys()))
        if not all_symbols:
            return 0.0

        total_abs_diff = sum(
            abs(target_weights.get(s, 0.0) - current_weights.get(s, 0.0))
            for s in all_symbols
        )
        return float(total_abs_diff / 2.0)

    @staticmethod
    def compute_rebalance_costs(
        current_positions: Dict[str, PortfolioPosition],
        target_positions: Dict[str, PortfolioTarget],
        total_capital: float,
        transaction_cost_bps: float = 10.0,
        slippage_bps: float = 5.0,
    ) -> Tuple[float, float, float]:
        """
        Compute turnover, gross traded value, and total estimated transaction cost.

        Parameters:
            current_positions: Current holdings.
            target_positions: Target holdings.
            total_capital: Total portfolio equity value.
            transaction_cost_bps: Broker/exchange fee in basis points.
            slippage_bps: Market impact / slippage in basis points.

        Returns:
            Tuple of (turnover: float, traded_value: float, estimated_cost: float)
        """
        if total_capital <= 0:
            return 0.0, 0.0, 0.0

        all_symbols = set(current_positions.keys()).union(set(target_positions.keys()))
        total_trade_value = 0.0

        for sym in all_symbols:
            curr_val = current_positions[sym].value if sym in current_positions else 0.0
            tgt_val = target_positions[sym].target_value if sym in target_positions else 0.0
            delta = abs(tgt_val - curr_val)
            total_trade_value += delta

        turnover = total_trade_value / (2.0 * total_capital)
        total_rate = (transaction_cost_bps + slippage_bps) / 10000.0
        estimated_cost = total_trade_value * total_rate

        return float(turnover), float(total_trade_value), float(estimated_cost)
