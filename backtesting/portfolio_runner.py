"""
backtesting/portfolio_runner.py — Portfolio construction adapter for backtesting.

Consumes Step 7 PortfolioBuilder to translate RankedUniverse into risk-constrained
integer share allocations, treating Step 7 as an authoritative dependency.
"""
from __future__ import annotations

from typing import Dict, Optional
import pandas as pd

from portfolio.models import PortfolioBuildResult, PortfolioPosition
from portfolio.portfolio_builder import PortfolioBuilder
from portfolio.config import PortfolioConfig
from ranking.models import RankedUniverse
from backtesting.models import HoldingPosition


class PortfolioRunner:
    """
    Executes risk-constrained portfolio construction at rebalance timestamp T.
    Directly wraps Step 7 PortfolioBuilder.
    """

    def __init__(
        self,
        builder: Optional[PortfolioBuilder] = None,
        config: Optional[PortfolioConfig] = None,
    ) -> None:
        if builder is not None:
            self.builder = builder
        else:
            p_cfg = config or PortfolioConfig()
            self.builder = PortfolioBuilder(config=p_cfg)

    def build_target_portfolio(
        self,
        ranked_universe: RankedUniverse,
        market_bars_history: Dict[str, pd.DataFrame],
        total_capital: float,
        current_holdings: Dict[str, HoldingPosition],
        method: Optional[str] = None,
    ) -> PortfolioBuildResult:
        """
        Translate current holdings and ranked universe into target allocations.

        Parameters:
            ranked_universe: Step 6 RankedUniverse at timestamp T.
            market_bars_history: Historical market bars strictly <= T.
            total_capital: Current total portfolio equity (cash + position values).
            current_holdings: Active portfolio holdings mapped from accounting.
            method: Allocation method ('constrained', 'equal_weight', 'score_weighted', 'inverse_volatility').

        Returns:
            Strongly typed PortfolioBuildResult from Step 7.
        """
        # Convert backtesting HoldingPosition or pass through Step 7 PortfolioPosition instances
        current_portfolio_positions: Dict[str, PortfolioPosition] = {}
        for sym, pos in current_holdings.items():
            if isinstance(pos, PortfolioPosition):
                if pos.shares > 0:
                    current_portfolio_positions[sym] = pos
            elif pos.shares > 0:
                current_portfolio_positions[sym] = PortfolioPosition(
                    symbol=sym,
                    shares=pos.shares,
                    price=getattr(pos, "current_price", getattr(pos, "price", 0.0)),
                    value=getattr(pos, "market_value", getattr(pos, "value", 0.0)),
                    weight=pos.weight,
                )

        return self.builder.build_portfolio(
            ranked_universe=ranked_universe,
            market_bars=market_bars_history,
            total_capital=total_capital,
            current_positions=current_portfolio_positions,
            method=method,
        )
