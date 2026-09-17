"""
portfolio/config.py — Portfolio Construction Configuration and Risk Constraints.

Defines:
  - PortfolioConfig: Central configuration for long-only cash equity portfolio construction.
  - Sensible conservative baseline defaults for position limits, cash reserves,
    sector concentration, transaction costs, and liquidity limits.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PortfolioConfig:
    """
    Configuration parameters for long-only cash equity portfolio construction.
    
    All limits are explicit, documented, and enforced deterministically.
    No leverage, no short selling, no margin, no derivatives.
    """
    # Position count limits
    max_positions: int = 5
    min_positions: int = 1

    # Weight constraints (fractions in [0.0, 1.0])
    max_single_stock_weight: float = 0.35  # Max 35% in any single instrument
    min_position_weight: float = 0.05      # Min 5% threshold to avoid dust positions
    max_sector_weight: float = 0.50        # Max 50% exposure to any single sector
    max_gross_exposure: float = 0.95       # Max 95% total invested equity (leaving 5% cash buffer)
    min_cash_weight: float = 0.05          # Min 5% cash reserve requirement

    # Turnover and rebalance constraints
    max_turnover: float = 1.0              # Max one-way turnover per rebalance (1.0 = 100% portfolio turnover)
    volatility_target: Optional[float] = None  # Optional annualized volatility ceiling

    # Execution and cost parameters (research assumptions)
    minimum_trade_value: float = 1000.0    # Min INR value required to trade an instrument
    transaction_cost_bps: float = 10.0     # 10 bps estimated broker/exchange transaction fee
    slippage_bps: float = 5.0              # 5 bps estimated market impact / execution slippage
    liquidity_participation_limit: float = 0.05  # Max 5% of 20-day median daily turnover

    # Optimization parameters
    risk_aversion: float = 1.0             # Mean-variance tradeoff parameter (lambda)
    default_allocation_method: str = "constrained"  # 'equal_weight', 'score_weighted', 'inverse_volatility', 'constrained'

    def __post_init__(self) -> None:
        if self.max_positions < self.min_positions:
            raise ValueError(f"max_positions ({self.max_positions}) must be >= min_positions ({self.min_positions})")
        if self.max_single_stock_weight <= 0.0 or self.max_single_stock_weight > 1.0:
            raise ValueError("max_single_stock_weight must be in (0.0, 1.0]")
        if self.max_gross_exposure <= 0.0 or self.max_gross_exposure > 1.0:
            raise ValueError("max_gross_exposure must be in (0.0, 1.0]")
        if self.min_cash_weight < 0.0 or self.min_cash_weight >= 1.0:
            raise ValueError("min_cash_weight must be in [0.0, 1.0)")
        if self.max_gross_exposure + self.min_cash_weight > 1.0001:
            raise ValueError("max_gross_exposure + min_cash_weight cannot exceed 1.0")
        if self.default_allocation_method not in ("equal_weight", "score_weighted", "inverse_volatility", "constrained"):
            raise ValueError(f"Unknown allocation method: {self.default_allocation_method}")
