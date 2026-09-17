"""
portfolio/allocators.py — Standard Portfolio Allocation Engines.

Implements:
  1. EqualWeightAllocator
  2. ScoreWeightedAllocator
  3. InverseVolatilityAllocator

All allocators strictly obey long-only, gross exposure, single-stock,
sector, and minimum cash constraints.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List, Optional
import numpy as np
import pandas as pd

from portfolio.config import PortfolioConfig
from portfolio.constraints import PortfolioConstraintValidator
from portfolio.models import (
    InfeasibilityReason,
    PortfolioAllocation,
    PortfolioCandidate,
)


class IPortfolioAllocator(ABC):
    """Abstract interface for portfolio allocation methods."""

    @abstractmethod
    def allocate(
        self,
        candidates: List[PortfolioCandidate],
        config: PortfolioConfig,
        current_weights: Optional[Dict[str, float]] = None,
        total_capital: float = 100_000.0,
    ) -> PortfolioAllocation:
        """Produce target portfolio weights from eligible candidates."""
        raise NotImplementedError


def _apply_heuristic_constraints(
    raw_weights: Dict[str, float],
    candidates: List[PortfolioCandidate],
    config: PortfolioConfig,
) -> Dict[str, float]:
    """
    Project raw weights into the feasible polytope defined by:
      - w_i <= max_single_stock_weight
      - sum(w_i in sector) <= max_sector_weight
      - sum(w_i) <= max_gross_exposure
    """
    weights = dict(raw_weights)
    sec_map = {c.symbol: c.sector or "Unclassified" for c in candidates}

    # 1. Cap single stock weights
    for sym in list(weights.keys()):
        if weights[sym] > config.max_single_stock_weight:
            weights[sym] = config.max_single_stock_weight

    # 2. Cap sector weights
    for _ in range(5):  # Iterative projection
        sec_sums: Dict[str, float] = {}
        for sym, w in weights.items():
            sec = sec_map.get(sym, "Unclassified")
            sec_sums[sec] = sec_sums.get(sec, 0.0) + w

        adjusted = False
        for sec, total_sec in sec_sums.items():
            if total_sec > config.max_sector_weight + 1e-5:
                scale = config.max_sector_weight / total_sec
                for sym in weights:
                    if sec_map.get(sym) == sec:
                        weights[sym] *= scale
                adjusted = True
        if not adjusted:
            break

    # 3. Scale to gross exposure ceiling if exceeded
    tot_w = sum(weights.values())
    if tot_w > config.max_gross_exposure + 1e-5:
        scale = config.max_gross_exposure / tot_w
        for sym in weights:
            weights[sym] *= scale

    # 4. Filter out tiny residual dust
    for sym in list(weights.keys()):
        if weights[sym] < config.min_position_weight - 1e-4:
            weights[sym] = 0.0

    return {s: w for s, w in weights.items() if w > 1e-5}


class EqualWeightAllocator(IPortfolioAllocator):
    """Allocates available equity capital equally among top eligible stocks."""

    def allocate(
        self,
        candidates: List[PortfolioCandidate],
        config: PortfolioConfig,
        current_weights: Optional[Dict[str, float]] = None,
        total_capital: float = 100_000.0,
    ) -> PortfolioAllocation:
        eligible = [c for c in candidates if c.is_eligible]
        if len(eligible) < config.min_positions:
            return PortfolioAllocation(
                target_weights={},
                cash_weight=1.0,
                method="equal_weight",
                status="INFEASIBLE",
                infeasibility_reason=InfeasibilityReason.INSUFFICIENT_ELIGIBLE_STOCKS,
            )

        # Sort by opportunity score desc, then predicted return desc, then symbol asc
        sorted_candidates = sorted(
            eligible,
            key=lambda c: (c.opportunity_score or 0.0, c.predicted_return or 0.0, -ord(c.symbol[0])),
            reverse=True,
        )

        selected = sorted_candidates[: config.max_positions]
        k = len(selected)

        # Base equal weight
        base_w = min(config.max_single_stock_weight, config.max_gross_exposure / k)
        raw_weights = {c.symbol: base_w for c in selected}

        # Enforce sector and gross exposure limits
        final_weights = _apply_heuristic_constraints(raw_weights, selected, config)
        cash_w = max(config.min_cash_weight, 1.0 - sum(final_weights.values()))

        # Feasibility check
        sec_map = {c.symbol: c.sector or "Unclassified" for c in selected}
        is_feas, reason, msg = PortfolioConstraintValidator.validate_portfolio_weights(
            weights=final_weights,
            cash_weight=cash_w,
            config=config,
            candidate_sectors=sec_map,
            total_capital=total_capital,
            current_weights=current_weights,
        )

        return PortfolioAllocation(
            target_weights=final_weights,
            cash_weight=cash_w,
            method="equal_weight",
            status="FEASIBLE" if is_feas else "INFEASIBLE",
            infeasibility_reason=reason,
        )


class ScoreWeightedAllocator(IPortfolioAllocator):
    """Allocates capital proportional to positive Opportunity Scores."""

    def allocate(
        self,
        candidates: List[PortfolioCandidate],
        config: PortfolioConfig,
        current_weights: Optional[Dict[str, float]] = None,
        total_capital: float = 100_000.0,
    ) -> PortfolioAllocation:
        eligible = [c for c in candidates if c.is_eligible and (c.opportunity_score or 0.0) > 0.0]
        if len(eligible) < config.min_positions:
            return PortfolioAllocation(
                target_weights={},
                cash_weight=1.0,
                method="score_weighted",
                status="INFEASIBLE",
                infeasibility_reason=InfeasibilityReason.INSUFFICIENT_ELIGIBLE_STOCKS,
            )

        sorted_candidates = sorted(
            eligible,
            key=lambda c: (c.opportunity_score or 0.0, c.predicted_return or 0.0),
            reverse=True,
        )[: config.max_positions]

        total_score = sum(c.opportunity_score or 0.0 for c in sorted_candidates)
        if total_score <= 1e-8:
            return EqualWeightAllocator().allocate(candidates, config, current_weights, total_capital)

        raw_weights: Dict[str, float] = {}
        for c in sorted_candidates:
            raw_weights[c.symbol] = ((c.opportunity_score or 0.0) / total_score) * config.max_gross_exposure

        final_weights = _apply_heuristic_constraints(raw_weights, sorted_candidates, config)
        cash_w = max(config.min_cash_weight, 1.0 - sum(final_weights.values()))

        sec_map = {c.symbol: c.sector or "Unclassified" for c in sorted_candidates}
        is_feas, reason, msg = PortfolioConstraintValidator.validate_portfolio_weights(
            weights=final_weights,
            cash_weight=cash_w,
            config=config,
            candidate_sectors=sec_map,
            total_capital=total_capital,
            current_weights=current_weights,
        )

        return PortfolioAllocation(
            target_weights=final_weights,
            cash_weight=cash_w,
            method="score_weighted",
            status="FEASIBLE" if is_feas else "INFEASIBLE",
            infeasibility_reason=reason,
        )


class InverseVolatilityAllocator(IPortfolioAllocator):
    """Allocates capital inversely proportional to historical return volatility (1 / sigma)."""

    def allocate(
        self,
        candidates: List[PortfolioCandidate],
        config: PortfolioConfig,
        current_weights: Optional[Dict[str, float]] = None,
        total_capital: float = 100_000.0,
    ) -> PortfolioAllocation:
        eligible = [c for c in candidates if c.is_eligible]
        if len(eligible) < config.min_positions:
            return PortfolioAllocation(
                target_weights={},
                cash_weight=1.0,
                method="inverse_volatility",
                status="INFEASIBLE",
                infeasibility_reason=InfeasibilityReason.INSUFFICIENT_ELIGIBLE_STOCKS,
            )

        sorted_candidates = sorted(
            eligible,
            key=lambda c: (c.opportunity_score or 0.0, c.predicted_return or 0.0),
            reverse=True,
        )[: config.max_positions]

        # Extract volatilities safely
        vols = []
        for c in sorted_candidates:
            v = c.volatility
            if v is None or pd.isna(v) or v <= 1e-6:
                vols.append(0.02)  # Conservative fallback
            else:
                vols.append(float(v))

        inv_vols = [1.0 / (v + 1e-6) for v in vols]
        sum_inv = sum(inv_vols)

        raw_weights: Dict[str, float] = {}
        for idx, c in enumerate(sorted_candidates):
            raw_weights[c.symbol] = (inv_vols[idx] / sum_inv) * config.max_gross_exposure

        final_weights = _apply_heuristic_constraints(raw_weights, sorted_candidates, config)
        cash_w = max(config.min_cash_weight, 1.0 - sum(final_weights.values()))

        sec_map = {c.symbol: c.sector or "Unclassified" for c in sorted_candidates}
        is_feas, reason, msg = PortfolioConstraintValidator.validate_portfolio_weights(
            weights=final_weights,
            cash_weight=cash_w,
            config=config,
            candidate_sectors=sec_map,
            total_capital=total_capital,
            current_weights=current_weights,
        )

        return PortfolioAllocation(
            target_weights=final_weights,
            cash_weight=cash_w,
            method="inverse_volatility",
            status="FEASIBLE" if is_feas else "INFEASIBLE",
            infeasibility_reason=reason,
        )
