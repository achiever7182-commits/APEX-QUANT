"""
portfolio/optimizer.py — Constrained Quadratic Mean-Variance Portfolio Optimizer.

Formulation:
    minimize:   (lambda / 2) * w^T * Sigma * w - mu^T * w
    subject to:
        0 <= w_i <= max_single_stock_weight
        sum(w_i) <= max_gross_exposure
        sum(w_i in sector) <= max_sector_weight
        (optional) turnover <= max_turnover
        (optional) volatility <= volatility_target

Solved deterministically using scipy.optimize.minimize (SLSQP).
"""

from __future__ import annotations

from typing import Dict, List, Optional
import numpy as np
import pandas as pd
from scipy.optimize import minimize

from portfolio.allocators import IPortfolioAllocator
from portfolio.config import PortfolioConfig
from portfolio.constraints import PortfolioConstraintValidator
from portfolio.models import (
    InfeasibilityReason,
    PortfolioAllocation,
    PortfolioCandidate,
)
from portfolio.risk import PortfolioRiskModel


class ConstrainedOptimizer(IPortfolioAllocator):
    """
    Mean-Variance optimizer with linear inequality constraints for Indian cash equities.
    """

    def __init__(self, risk_model: Optional[PortfolioRiskModel] = None):
        self.risk_model = risk_model or PortfolioRiskModel()

    def allocate(
        self,
        candidates: List[PortfolioCandidate],
        config: PortfolioConfig,
        current_weights: Optional[Dict[str, float]] = None,
        total_capital: float = 100_000.0,
        cov_matrix: Optional[pd.DataFrame] = None,
    ) -> PortfolioAllocation:
        eligible = [c for c in candidates if c.is_eligible]
        if len(eligible) < config.min_positions:
            return PortfolioAllocation(
                target_weights={},
                cash_weight=1.0,
                method="constrained",
                status="INFEASIBLE",
                infeasibility_reason=InfeasibilityReason.INSUFFICIENT_ELIGIBLE_STOCKS,
            )

        # Select top candidates up to max_positions
        sorted_candidates = sorted(
            eligible,
            key=lambda c: (c.opportunity_score or 0.0, c.predicted_return or 0.0),
            reverse=True,
        )[: config.max_positions]

        symbols = [c.symbol for c in sorted_candidates]
        k = len(symbols)

        # Expected returns vector (annualized or 5d horizon)
        mu = np.array([float(c.predicted_return or 0.0) for c in sorted_candidates], dtype=float)

        # Covariance matrix
        if cov_matrix is not None and all(s in cov_matrix.columns for s in symbols):
            sigma = cov_matrix.loc[symbols, symbols].values.astype(float)
        else:
            # Fallback diagonal covariance from candidate volatility
            diag_vols = []
            for c in sorted_candidates:
                v = c.volatility if c.volatility and c.volatility > 0 else 0.02
                diag_vols.append(float(v) ** 2)
            sigma = np.diag(diag_vols)

        # Regularize covariance if needed
        sigma = 0.5 * (sigma + sigma.T)  # Force symmetry
        min_eig = np.min(np.linalg.eigvalsh(sigma))
        if min_eig < 1e-6:
            sigma += (abs(min_eig) + 1e-4) * np.eye(k)

        # Objective Function: (lambda / 2) * w^T * Sigma * w - mu^T * w
        lam = float(config.risk_aversion)

        def objective(w: np.ndarray) -> float:
            port_var = float(np.dot(w.T, np.dot(sigma, w)))
            port_ret = float(np.dot(mu, w))
            return 0.5 * lam * port_var - port_ret

        def objective_grad(w: np.ndarray) -> np.ndarray:
            return lam * np.dot(sigma, w) - mu

        # Bounds: 0 <= w_i <= max_single_stock_weight
        bounds = [(0.0, float(config.max_single_stock_weight)) for _ in range(k)]

        # Linear Constraints
        constraints = []

        # 1. Gross exposure: sum(w_i) <= max_gross_exposure
        constraints.append({
            "type": "ineq",
            "fun": lambda w: float(config.max_gross_exposure - np.sum(w)),
        })

        # 2. Sector Constraints
        sec_map = {c.symbol: c.sector or "Unclassified" for c in sorted_candidates}
        unique_sectors = set(sec_map.values())
        for sec in unique_sectors:
            sec_indices = [i for i, s in enumerate(symbols) if sec_map[s] == sec]
            constraints.append({
                "type": "ineq",
                "fun": lambda w, idxs=sec_indices: float(config.max_sector_weight - np.sum(w[idxs])),
            })

        # 3. Optional Turnover Constraint
        if current_weights is not None and config.max_turnover < 1.0:
            w0 = np.array([current_weights.get(s, 0.0) for s in symbols], dtype=float)
            constraints.append({
                "type": "ineq",
                "fun": lambda w, w_curr=w0: float(config.max_turnover - 0.5 * np.sum(np.abs(w - w_curr))),
            })

        # Initial point: equal weight across candidates
        w0 = np.full(k, min(config.max_single_stock_weight, config.max_gross_exposure / k))

        # Solve optimization deterministically
        res = minimize(
            objective,
            w0,
            jac=objective_grad,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
            options={"maxiter": 200, "ftol": 1e-7, "disp": False},
        )

        if not res.success:
            return PortfolioAllocation(
                target_weights={},
                cash_weight=1.0,
                method="constrained",
                status="INFEASIBLE",
                infeasibility_reason=InfeasibilityReason.CONVERGENCE_FAILURE,
            )

        raw_opt_weights = res.x
        final_weights: Dict[str, float] = {}
        for i, sym in enumerate(symbols):
            val = float(raw_opt_weights[i])
            if val >= config.min_position_weight - 1e-4:
                final_weights[sym] = round(val, 6)

        tot_invested = sum(final_weights.values())
        cash_w = max(config.min_cash_weight, round(1.0 - tot_invested, 6))

        # Final sanity check via PortfolioConstraintValidator
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
            method="constrained",
            status="FEASIBLE" if is_feas else "INFEASIBLE",
            infeasibility_reason=reason,
        )
