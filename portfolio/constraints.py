"""
portfolio/constraints.py — Portfolio Constraint Enforcement and Feasibility Validation.

Validates:
  - Candidate-level constraints (price, prediction, volatility, sector, liquidity)
  - Portfolio-level weight constraints (long-only, single-stock, sector, cash, gross exposure, count)
  - Liquidity participation capacity and rebalance turnover limits
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

from portfolio.config import PortfolioConfig
from portfolio.models import (
    CandidateRejectionReason,
    InfeasibilityReason,
    PortfolioCandidate,
)


class PortfolioConstraintValidator:
    """
    Enforces quantitative portfolio constraints and candidate eligibility.
    """

    @staticmethod
    def validate_candidate(
        candidate: PortfolioCandidate,
        config: Optional[PortfolioConfig] = None,
    ) -> Tuple[bool, Optional[CandidateRejectionReason]]:
        """
        Validate whether an individual instrument is qualified for portfolio consideration.
        """
        # 1. Check prior eligibility flag
        if not candidate.is_eligible:
            return False, candidate.rejection_reason or CandidateRejectionReason.OTHER

        # 2. Check price validity
        price = candidate.current_price
        if price is None or pd.isna(price) or float(price) <= 0.0 or np.isinf(price):
            return False, CandidateRejectionReason.MISSING_PRICE

        # 3. Check ML predicted return validity
        pred = candidate.predicted_return
        if pred is None or pd.isna(pred) or np.isinf(pred):
            return False, CandidateRejectionReason.INVALID_PREDICTION

        # 4. Check volatility validity (if present)
        vol = candidate.volatility
        if vol is not None:
            if pd.isna(vol) or float(vol) < 0.0 or np.isinf(vol):
                return False, CandidateRejectionReason.INVALID_VOLATILITY

        # 5. Check sector validity
        sec = candidate.sector
        if sec is None or pd.isna(sec) or str(sec).strip() in ("", "None", "Unknown", "Unclassified"):
            return False, CandidateRejectionReason.INVALID_SECTOR

        # 6. Check opportunity score validity
        score = candidate.opportunity_score
        if score is not None and not pd.isna(score) and float(score) < 0.0:
            return False, CandidateRejectionReason.BELOW_MIN_SCORE

        return True, None

    @staticmethod
    def validate_portfolio_weights(
        weights: Dict[str, float],
        cash_weight: float,
        config: PortfolioConfig,
        candidate_sectors: Dict[str, str],
        candidate_turnovers: Optional[Dict[str, float]] = None,
        total_capital: float = 100_000.0,
        current_weights: Optional[Dict[str, float]] = None,
    ) -> Tuple[bool, Optional[InfeasibilityReason], str]:
        """
        Verify that a candidate set of target portfolio weights strictly satisfies all constraints.
        """
        active_weights = {s: w for s, w in weights.items() if w > 1e-4}

        # 1. Long-Only Constraint (no negative weights)
        for sym, w in weights.items():
            if w < -1e-5:
                return False, InfeasibilityReason.OTHER, f"Negative weight detected for {sym}: {w:.4f} (no short positions)"

        # 2. Minimum Cash Weight
        if cash_weight < config.min_cash_weight - 1e-4:
            return False, InfeasibilityReason.OTHER, f"Cash weight ({cash_weight:.4f}) below minimum ({config.min_cash_weight:.4f})"

        # 3. Maximum Gross Exposure (no leverage)
        gross_exposure = sum(weights.values())
        if gross_exposure > config.max_gross_exposure + 1e-4:
            return False, InfeasibilityReason.OTHER, f"Gross exposure ({gross_exposure:.4f}) exceeds maximum ({config.max_gross_exposure:.4f})"

        # 4. Position Count Constraints
        n_pos = len(active_weights)
        if n_pos > config.max_positions:
            return False, InfeasibilityReason.OTHER, f"Position count ({n_pos}) exceeds max_positions ({config.max_positions})"
        if n_pos < config.min_positions and n_pos > 0:
            return False, InfeasibilityReason.INSUFFICIENT_ELIGIBLE_STOCKS, f"Position count ({n_pos}) below min_positions ({config.min_positions})"

        # 5. Single Stock Limits
        for sym, w in active_weights.items():
            if w > config.max_single_stock_weight + 1e-4:
                return False, InfeasibilityReason.OTHER, f"Stock {sym} weight ({w:.4f}) exceeds max_single_stock_weight ({config.max_single_stock_weight:.4f})"
            if w < config.min_position_weight - 1e-4:
                return False, InfeasibilityReason.OTHER, f"Stock {sym} weight ({w:.4f}) below min_position_weight ({config.min_position_weight:.4f})"

        # 6. Sector Constraints
        sector_weights: Dict[str, float] = {}
        for sym, w in active_weights.items():
            sec = candidate_sectors.get(sym, "Unclassified")
            sector_weights[sec] = sector_weights.get(sec, 0.0) + w

        for sec, sec_w in sector_weights.items():
            if sec_w > config.max_sector_weight + 1e-4:
                return False, InfeasibilityReason.SECTOR_CONSTRAINT_INFEASIBLE, f"Sector '{sec}' weight ({sec_w:.4f}) exceeds max_sector_weight ({config.max_sector_weight:.4f})"

        # 7. Liquidity Participation Constraints
        if candidate_turnovers:
            for sym, w in active_weights.items():
                pos_val = w * total_capital
                daily_turnover = candidate_turnovers.get(sym, 0.0)
                if daily_turnover > 0:
                    max_cap = daily_turnover * config.liquidity_participation_limit
                    if pos_val > max_cap + 1.0:
                        return False, InfeasibilityReason.LIQUIDITY_CONSTRAINT_INFEASIBLE, f"Stock {sym} value ({pos_val:,.0f}) exceeds liquidity participation limit ({max_cap:,.0f})"

        # 8. Turnover Constraint
        if current_weights is not None and config.max_turnover < 1.0:
            all_syms = set(active_weights.keys()).union(set(current_weights.keys()))
            turnover = 0.5 * sum(abs(active_weights.get(s, 0.0) - current_weights.get(s, 0.0)) for s in all_syms)
            if turnover > config.max_turnover + 1e-4:
                return False, InfeasibilityReason.TURNOVER_CONSTRAINT_INFEASIBLE, f"Turnover ({turnover:.4f}) exceeds max_turnover ({config.max_turnover:.4f})"

        return True, None, "OK"
