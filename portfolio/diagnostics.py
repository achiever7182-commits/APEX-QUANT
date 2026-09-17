"""
portfolio/diagnostics.py — Diagnostic Engine for Portfolio Concentration and Risk Metrics.

Computes:
  - Herfindahl-Hirschman Index (HHI) concentration
  - Sector exposure distribution and largest sector
  - Single-stock concentration and largest position
  - Liquidity participation capacity utilization
  - Expected return, portfolio volatility, and return-to-risk ratio
"""

from __future__ import annotations

from typing import Dict, List, Optional
import numpy as np

from portfolio.models import (
    PortfolioDiagnostics,
    PortfolioPosition,
    PortfolioRiskMetrics,
    PortfolioTarget,
)
from portfolio.risk import PortfolioRiskModel


class PortfolioDiagnosticsEngine:
    """
    Computes post-allocation diagnostic characteristics of constructed portfolios.
    """

    @staticmethod
    def compute_hhi(weights: Dict[str, float]) -> float:
        """
        Calculate Herfindahl-Hirschman Index (HHI) of position weights.
        Normalized scale: sum((w_i / sum(w))^2). Bounded in [1/N, 1.0].
        """
        pos_w = [w for w in weights.values() if w > 1e-5]
        if not pos_w:
            return 0.0
        tot = sum(pos_w)
        if tot <= 1e-8:
            return 0.0
        norm_w = [w / tot for w in pos_w]
        return float(sum(w ** 2 for w in norm_w))

    @staticmethod
    def evaluate_diagnostics(
        target_positions: Dict[str, PortfolioTarget],
        cash: float,
        total_capital: float,
        turnover: float,
        estimated_cost: float,
        turnover_by_symbol: Optional[Dict[str, float]] = None,
    ) -> PortfolioDiagnostics:
        """
        Assemble comprehensive portfolio diagnostics from constructed targets.
        """
        weights = {sym: t.target_weight for sym, t in target_positions.items()}
        n_pos = len([w for w in weights.values() if w > 1e-5])
        gross_exp = float(sum(weights.values()))
        cash_w = float(cash / total_capital) if total_capital > 0 else 1.0

        # Sector weights
        sec_weights: Dict[str, float] = {}
        for sym, t in target_positions.items():
            sec = t.sector or "Unclassified"
            sec_weights[sec] = sec_weights.get(sec, 0.0) + t.target_weight

        largest_pos = max(weights.items(), key=lambda x: x[1])[0] if weights else None
        max_pos_w = float(max(weights.values())) if weights else 0.0

        largest_sec = max(sec_weights.items(), key=lambda x: x[1])[0] if sec_weights else None

        # Liquidity utilization
        liq_util: Dict[str, float] = {}
        if turnover_by_symbol:
            for sym, t in target_positions.items():
                daily_turnover = turnover_by_symbol.get(sym, 0.0)
                if daily_turnover > 0:
                    liq_util[sym] = float(t.target_value / daily_turnover)

        hhi = PortfolioDiagnosticsEngine.compute_hhi(weights)

        return PortfolioDiagnostics(
            position_count=n_pos,
            cash_weight=cash_w,
            gross_exposure=gross_exp,
            turnover=turnover,
            estimated_transaction_cost=estimated_cost,
            hhi_concentration=hhi,
            max_position_weight=max_pos_w,
            largest_position=largest_pos,
            largest_sector=largest_sec,
            sector_weights=sec_weights,
            liquidity_utilization=liq_util,
            residual_cash=cash,
        )
