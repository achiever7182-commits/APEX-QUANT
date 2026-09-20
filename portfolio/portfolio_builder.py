"""
portfolio/portfolio_builder.py — Master Orchestrator for Indian Cash Equity Portfolio Construction.

Consumes:
  - Step 6 RankedUniverse
  - Current portfolio state (existing positions & cash)
  - Historical market bars (strictly <= T)

Produces:
  - Integer share allocations
  - Actual weights and residual cash
  - Transaction costs and turnover
  - Risk metrics and diagnostics
  - Explicit candidate rejection logging

Zero trade execution. Zero broker connections. Zero lookahead bias.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union
import numpy as np
import pandas as pd

from portfolio.allocators import (
    EqualWeightAllocator,
    InverseVolatilityAllocator,
    IPortfolioAllocator,
    ScoreWeightedAllocator,
)
from portfolio.config import PortfolioConfig
from portfolio.constraints import PortfolioConstraintValidator
from portfolio.cost_model import TransactionCostModel
from portfolio.diagnostics import PortfolioDiagnosticsEngine
from portfolio.models import (
    CandidateRejectionReason,
    InfeasibilityReason,
    PortfolioAllocation,
    PortfolioBuildResult,
    PortfolioCandidate,
    PortfolioDiagnostics,
    PortfolioPosition,
    PortfolioRiskMetrics,
    PortfolioTarget,
)
from portfolio.optimizer import ConstrainedOptimizer
from portfolio.risk import PortfolioRiskModel
from ranking.models import RankedUniverse

logger = logging.getLogger("apex_quant.portfolio")


class PortfolioBuilder:
    """
    Constructs long-only cash equity portfolios satisfying configured risk limits.
    """

    def __init__(
        self,
        config: Optional[PortfolioConfig] = None,
        risk_model: Optional[PortfolioRiskModel] = None,
    ):
        self.config = config or PortfolioConfig()
        self.risk_model = risk_model or PortfolioRiskModel()
        self.allocators: Dict[str, IPortfolioAllocator] = {
            "equal_weight": EqualWeightAllocator(),
            "score_weighted": ScoreWeightedAllocator(),
            "inverse_volatility": InverseVolatilityAllocator(),
            "constrained": ConstrainedOptimizer(risk_model=self.risk_model),
        }

    def build_portfolio(
        self,
        ranked_universe: RankedUniverse,
        market_bars: Dict[str, pd.DataFrame],
        total_capital: float = 100_000.0,
        current_positions: Optional[Dict[str, PortfolioPosition]] = None,
        method: Optional[str] = None,
    ) -> PortfolioBuildResult:
        """
        Construct a constrained target portfolio from a Step 6 RankedUniverse.

        Parameters:
            ranked_universe: Step 6 RankedUniverse at timestamp T.
            market_bars: Historical market bars up to T.
            total_capital: Total portfolio value in base currency (INR).
            current_positions: Existing instrument positions before rebalance.
            method: Allocation method ('equal_weight', 'score_weighted', 'inverse_volatility', 'constrained').

        Returns:
            Strongly typed PortfolioBuildResult.
        """
        eval_ts = ranked_universe.timestamp
        req_method = method or self.config.default_allocation_method
        curr_pos = current_positions or {}

        # Current weights (excluding cash)
        curr_weights = {s: p.weight for s, p in curr_pos.items()}

        # 1. Ingest Step 6 candidates and extract current prices strictly <= T
        candidates: List[PortfolioCandidate] = []
        rejected: List[PortfolioCandidate] = []

        # Latest prices as of eval_ts
        latest_prices: Dict[str, float] = {}
        latest_turnovers: Dict[str, float] = {}

        for sym, df in market_bars.items():
            if df.empty:
                continue
            df_c = df.copy()
            df_c["timestamp"] = pd.to_datetime(df_c["timestamp"])

            # Reconcile timezones
            if eval_ts.tzinfo is not None and df_c["timestamp"].dt.tz is None:
                df_c["timestamp"] = df_c["timestamp"].dt.tz_localize(eval_ts.tzinfo)
            elif eval_ts.tzinfo is None and df_c["timestamp"].dt.tz is not None:
                df_c["timestamp"] = df_c["timestamp"].dt.tz_localize(None)

            hist = df_c[df_c["timestamp"] <= eval_ts].sort_values("timestamp")
            if not hist.empty:
                latest_prices[sym] = float(hist.iloc[-1]["close"])
                if "volume" in hist.columns:
                    # 20-day median turnover
                    t_tail = hist.tail(20)
                    med_vol = float((t_tail["close"] * t_tail["volume"]).median())
                    latest_turnovers[sym] = med_vol

        # Build candidate models from ranked items
        for item in ranked_universe.ranked_items:
            sym = item.symbol
            price = latest_prices.get(sym)
            turnover = latest_turnovers.get(sym)

            cand = PortfolioCandidate(
                symbol=sym,
                timestamp=eval_ts,
                sector=item.sector,
                rank=item.rank,
                predicted_return=item.predicted_return,
                opportunity_score=item.opportunity_score,
                volatility=item.scoring_components.risk_adjusted_score if item.scoring_components else None,
                liquidity=turnover,
                current_price=price,
                is_eligible=item.is_eligible,
                rejection_reason=(
                    CandidateRejectionReason[item.rejection_reason.value]
                    if item.rejection_reason and item.rejection_reason.value in CandidateRejectionReason.__members__
                    else (CandidateRejectionReason(item.rejection_reason.value) if item.rejection_reason and item.rejection_reason.value in [e.value for e in CandidateRejectionReason] else (CandidateRejectionReason.OTHER if item.rejection_reason else None))
                ),
            )

            # Validate against portfolio-level candidate constraints
            is_valid, rej_reason = PortfolioConstraintValidator.validate_candidate(cand, self.config)
            if is_valid:
                candidates.append(cand)
            else:
                cand.is_eligible = False
                cand.rejection_reason = rej_reason
                rejected.append(cand)

        # 2. Check eligible candidate count
        if len(candidates) < self.config.min_positions:
            logger.warning(
                f"Insufficient eligible candidates ({len(candidates)} < {self.config.min_positions}). Holding 100% cash."
            )
            return PortfolioBuildResult(
                timestamp=eval_ts,
                total_capital=total_capital,
                cash=total_capital,
                cash_weight=1.0,
                gross_exposure=0.0,
                allocated_value=0.0,
                requested_method=req_method,
                allocation_method="cash_only",
                fallback_reason=f"Insufficient eligible candidates ({len(candidates)} < {self.config.min_positions})",
                candidate_count=len(ranked_universe.ranked_items),
                selected_count=0,
                positions={},
                risk_metrics=PortfolioRiskMetrics(0.0, 0.0, 0.0),
                diagnostics=PortfolioDiagnostics(0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, residual_cash=total_capital),
                rejected_candidates=rejected,
            )

        # 3. Compute point-in-time covariance matrix
        candidate_symbols = [c.symbol for c in candidates]
        cov_matrix, is_fallback_cov = self.risk_model.compute_covariance_matrix(
            market_bars=market_bars,
            symbols=candidate_symbols,
            as_of_date=eval_ts,
            lookback_bars=60,
        )

        # 4. Allocation with Deterministic Fallback Hierarchy
        # Hierarchy: constrained -> score_weighted -> equal_weight
        fallback_chain = ["constrained", "score_weighted", "equal_weight"]
        if req_method in fallback_chain:
            start_idx = fallback_chain.index(req_method)
            methods_to_try = fallback_chain[start_idx:]
        else:
            methods_to_try = [req_method, "equal_weight"]

        actual_method = req_method
        fallback_reason: Optional[str] = None
        allocation: Optional[PortfolioAllocation] = None

        for m in methods_to_try:
            allocator = self.allocators.get(m, self.allocators["equal_weight"])
            if m == "constrained" and isinstance(allocator, ConstrainedOptimizer):
                alloc = allocator.allocate(
                    candidates=candidates,
                    config=self.config,
                    current_weights=curr_weights,
                    total_capital=total_capital,
                    cov_matrix=cov_matrix,
                )
            else:
                alloc = allocator.allocate(
                    candidates=candidates,
                    config=self.config,
                    current_weights=curr_weights,
                    total_capital=total_capital,
                )

            if alloc.status == "FEASIBLE" and len(alloc.target_weights) > 0:
                allocation = alloc
                actual_method = m
                break
            else:
                if fallback_reason is None:
                    fallback_reason = f"Method '{m}' was infeasible ({alloc.infeasibility_reason})"

        if allocation is None or len(allocation.target_weights) == 0:
            # All allocation methods failed
            return PortfolioBuildResult(
                timestamp=eval_ts,
                total_capital=total_capital,
                cash=total_capital,
                cash_weight=1.0,
                gross_exposure=0.0,
                allocated_value=0.0,
                requested_method=req_method,
                allocation_method="cash_only",
                fallback_reason="All allocation methods infeasible",
                candidate_count=len(ranked_universe.ranked_items),
                selected_count=0,
                positions={},
                risk_metrics=PortfolioRiskMetrics(0.0, 0.0, 0.0),
                diagnostics=PortfolioDiagnostics(0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, residual_cash=total_capital),
                rejected_candidates=rejected,
            )

        # 5. Convert weights to Integer Shares (floor rounding)
        # target_shares = floor(target_value / current_price)
        target_positions: Dict[str, PortfolioTarget] = {}
        allocated_val = 0.0

        for sym, w in sorted(allocation.target_weights.items()):
            price = latest_prices.get(sym, 0.0)
            cand_meta = next((c for c in candidates if c.symbol == sym), None)
            sector_name = cand_meta.sector if cand_meta else None
            exp_ret = cand_meta.predicted_return if cand_meta else None

            if price <= 0:
                continue

            target_dollar = w * total_capital
            shares = int(math.floor(target_dollar / price))
            actual_pos_val = shares * price

            # Compute delta vs current position
            curr_shares = curr_pos[sym].shares if sym in curr_pos else 0
            curr_val = curr_pos[sym].value if sym in curr_pos else 0.0
            d_shares = shares - curr_shares
            d_val = actual_pos_val - curr_val

            if shares > 0 or curr_shares > 0:
                target_positions[sym] = PortfolioTarget(
                    symbol=sym,
                    target_weight=actual_pos_val / total_capital if total_capital > 0 else 0.0,
                    target_shares=shares,
                    target_value=actual_pos_val,
                    current_price=price,
                    sector=sector_name,
                    expected_return=exp_ret,
                    delta_shares=d_shares,
                    delta_value=d_val,
                )
                allocated_val += actual_pos_val

        # 6. Rebalance Costs and Turnover Calculation
        turnover, total_traded_val, est_cost = TransactionCostModel.compute_rebalance_costs(
            current_positions=curr_pos,
            target_positions=target_positions,
            total_capital=total_capital,
            transaction_cost_bps=self.config.transaction_cost_bps,
            slippage_bps=self.config.slippage_bps,
        )

        # 7. Residual Cash Management
        # Ensure cash is non-negative
        cash = total_capital - allocated_val - est_cost
        if cash < 0.0:
            # Reduce largest position by 1 share until cash >= 0
            while cash < 0.0 and any(p.target_shares > 0 for p in target_positions.values()):
                largest_pos_sym = max(target_positions.items(), key=lambda x: x[1].target_value)[0]
                p = target_positions[largest_pos_sym]
                p.target_shares -= 1
                p.target_value = p.target_shares * p.current_price
                p.target_weight = p.target_value / total_capital
                p.delta_shares = p.target_shares - (curr_pos[largest_pos_sym].shares if largest_pos_sym in curr_pos else 0)
                p.delta_value = p.target_value - (curr_pos[largest_pos_sym].value if largest_pos_sym in curr_pos else 0.0)
                allocated_val = sum(pos.target_value for pos in target_positions.values())
                cash = total_capital - allocated_val - est_cost

        cash = max(0.0, cash)
        cash_w = cash / total_capital if total_capital > 0 else 1.0
        gross_exp = sum(p.target_weight for p in target_positions.values())

        # 8. Portfolio Risk Metrics
        selected_symbols = list(target_positions.keys())
        w_vec = np.array([target_positions[s].target_weight for s in selected_symbols], dtype=float)
        exp_ret_vec = np.array([target_positions[s].expected_return or 0.0 for s in selected_symbols], dtype=float)

        if len(selected_symbols) > 0 and all(s in cov_matrix.columns for s in selected_symbols):
            sub_cov = cov_matrix.loc[selected_symbols, selected_symbols].values
            port_vol = self.risk_model.calculate_portfolio_volatility(w_vec, sub_cov)
            mrc_dict, prc_dict = self.risk_model.calculate_risk_contributions(w_vec, sub_cov, selected_symbols)
            sec_lookup = {s: target_positions[s].sector or "Unclassified" for s in selected_symbols}
            sec_prc = self.risk_model.calculate_sector_risk_contributions(prc_dict, sec_lookup)
        else:
            port_vol = 0.0
            mrc_dict = {s: 0.0 for s in selected_symbols}
            prc_dict = {s: 0.0 for s in selected_symbols}
            sec_prc = {}

        for s in selected_symbols:
            target_positions[s].risk_contribution = prc_dict.get(s, 0.0)

        port_exp_return = float(np.dot(w_vec, exp_ret_vec))
        ret_to_risk = (port_exp_return / port_vol) if port_vol > 1e-6 else 0.0

        risk_metrics = PortfolioRiskMetrics(
            expected_return=port_exp_return,
            portfolio_volatility=port_vol,
            return_to_risk_ratio=ret_to_risk,
            marginal_risk_contributions=mrc_dict,
            percentage_risk_contributions=prc_dict,
            sector_risk_contributions=sec_prc,
            is_covariance_fallback=is_fallback_cov,
        )

        # 9. Diagnostics
        diagnostics = PortfolioDiagnosticsEngine.evaluate_diagnostics(
            target_positions=target_positions,
            cash=cash,
            total_capital=total_capital,
            turnover=turnover,
            estimated_cost=est_cost,
            turnover_by_symbol=latest_turnovers,
        )

        return PortfolioBuildResult(
            timestamp=eval_ts,
            total_capital=total_capital,
            cash=cash,
            cash_weight=cash_w,
            gross_exposure=gross_exp,
            allocated_value=allocated_val,
            requested_method=req_method,
            allocation_method=actual_method,
            fallback_reason=fallback_reason,
            candidate_count=len(ranked_universe.ranked_items),
            selected_count=sum(1 for p in target_positions.values() if p.target_shares > 0),
            positions=target_positions,
            risk_metrics=risk_metrics,
            diagnostics=diagnostics,
            rejected_candidates=rejected,
        )
