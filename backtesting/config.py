"""
backtesting/config.py — Configuration parameters for APEX-QUANT Portfolio Backtesting Engine.

Defines rebalancing cadence, capital, execution conventions, cost assumptions,
and risk tolerances. All parameters are conservative and research-oriented.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from portfolio.config import PortfolioConfig
from ranking.config import RankingConfig


@dataclass
class BacktestConfig:
    """
    Central configuration for APEX-QUANT historical portfolio backtesting.

    Attributes:
        start_date: Start date of backtesting simulation (YYYY-MM-DD).
        end_date: End date of backtesting simulation (YYYY-MM-DD).
        initial_capital: Starting capital in INR (default: ₹10,00,000 / 10 Lakh).
        rebalance_frequency: Rebalance cadence ('daily', 'weekly', 'biweekly', 'monthly').
        execution_convention: Price convention for simulated fills:
            - 'next_open': Signal computed at close of T, filled at open of T+1.
            - 'next_close': Signal computed at close of T, filled at close of T+1.
            - 'close_t': Signal executed at close of T (documented close-on-close assumption).
            Default is 'next_open'.
        transaction_cost_bps: Assumed broker transaction fee in basis points (default: 10.0 bps = 0.10%).
        slippage_bps: Assumed execution slippage in basis points (default: 5.0 bps = 0.05%).
        liquidity_participation_limit: Max fraction of historical median daily volume/turnover
            allowed for a single position trade (default: 0.05 = 5%).
        default_allocation_method: Method from Step 7:
            - 'constrained' (mean-variance quadratic optimizer)
            - 'score_weighted' (normalized composite opportunity score)
            - 'inverse_volatility' (1 / volatility)
            - 'equal_weight' (1 / N)
        portfolio_config: Underlying PortfolioConfig from Step 7.
        ranking_config: Underlying RankingConfig from Step 6.
        allow_shorting: Long-only equity invariant (must remain False).
        allow_leverage: Leverage invariant (must remain False).
        allow_fractional: Whole-share invariant (must remain False).
        warmup_bars: Minimum historical bars required before the first trade (default: 60 bars).
    """
    start_date: str = "2023-06-01"
    end_date: str = "2024-04-30"
    initial_capital: float = 1_000_000.0
    rebalance_frequency: str = "weekly"
    execution_convention: str = "next_open"
    transaction_cost_bps: float = 10.0
    slippage_bps: float = 5.0
    liquidity_participation_limit: float = 0.05
    default_allocation_method: str = "constrained"

    portfolio_config: PortfolioConfig = field(default_factory=lambda: PortfolioConfig(
        max_positions=5,
        min_positions=1,
        max_single_stock_weight=0.35,
        max_sector_weight=0.55,
        max_gross_exposure=0.95,
        min_cash_weight=0.05,
        max_turnover=1.0,
        transaction_cost_bps=10.0,
        slippage_bps=5.0,
    ))

    ranking_config: RankingConfig = field(default_factory=lambda: RankingConfig(
        top_k=5,
        normalization_method="percentile",
    ))

    allow_shorting: bool = False
    allow_leverage: bool = False
    allow_fractional: bool = False
    warmup_bars: int = 60

    # Risk-free rate assumption (RBI 91-day T-bill baseline: 6.5%)
    risk_free_rate: float = 0.065

    # Performance calculation conventions
    cagr_convention: str = "trading"  # 'trading' (252 bars) or 'calendar' (365.25 days)

    # Point-in-time walk-forward ML configuration
    use_walk_forward_ml: bool = True
    ml_model_type: str = "ridge"  # 'ridge' (Linear shrinkage) or 'random_forest'
    ml_target_horizon: int = 5  # 5-day forward return target
    ml_min_train_samples: int = 100  # Minimum samples required before ML inference

    # Post-execution risk limits
    max_single_stock_weight: float = 0.35
    max_sector_weight: float = 0.55

