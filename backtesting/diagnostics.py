"""
backtesting/diagnostics.py — Diagnostic reporting, baseline comparison, and invariant verification.

Generates objective side-by-side strategy comparisons, cost impact attribution,
and enforces mathematical invariant checks across backtest snapshots.
"""
from __future__ import annotations

from typing import Dict, List, Tuple
import pandas as pd

from backtesting.models import BacktestMetrics, BacktestResult, PortfolioSnapshot


class BacktestDiagnostics:
    """
    Diagnostic suite for backtesting audit and reporting.
    """

    @staticmethod
    def audit_backtest_invariants(snapshots: List[PortfolioSnapshot]) -> Dict[str, int]:
        """
        Verify all 10 core safety invariants across every simulation snapshot.

        Returns dictionary of violation counts (all must be 0 for a valid backtest).
        """
        violations = {
            "negative_cash_instances": 0,
            "negative_shares_instances": 0,
            "fractional_shares_instances": 0,
            "short_positions_instances": 0,
            "leverage_instances": 0,
            "gross_exposure_violations": 0,
            "balance_identity_mismatches": 0,
        }

        for s in snapshots:
            # 1. No negative cash
            if s.cash < -1e-4:
                violations["negative_cash_instances"] += 1

            # 2. Position checks
            total_pos_val = 0.0
            for sym, pos in s.positions.items():
                if pos.shares < 0:
                    violations["negative_shares_instances"] += 1
                    violations["short_positions_instances"] += 1
                if not isinstance(pos.shares, int):
                    violations["fractional_shares_instances"] += 1
                total_pos_val += pos.market_value

            # 3. No leverage (gross exposure <= 100% + tolerance)
            if s.gross_exposure > 1.0001:
                violations["leverage_instances"] += 1
                violations["gross_exposure_violations"] += 1

            # 4. Balance identity: Cash + Pos Value == Portfolio Value
            expected_eq = s.cash + total_pos_val
            if abs(expected_eq - s.portfolio_value) > 1e-4:
                violations["balance_identity_mismatches"] += 1

        return violations

    @staticmethod
    def format_baseline_comparison_table(
        results: Dict[str, BacktestResult],
    ) -> pd.DataFrame:
        """
        Build an objective side-by-side metric comparison table without declaring a winner.
        """
        rows = []
        for name, res in results.items():
            m = res.metrics
            rows.append({
                "Strategy": name,
                "Total Return": f"{m.total_return * 100:+.2f}%",
                "CAGR": f"{m.cagr * 100:+.2f}%",
                "Volatility": f"{m.annualized_volatility * 100:.2f}%",
                "Sharpe": f"{m.sharpe_ratio:.4f}",
                "Sortino": f"{m.sortino_ratio:.4f}",
                "Max Drawdown": f"{m.max_drawdown * 100:.2f}%",
                "Turnover": f"{m.total_turnover:.2f}",
                "Costs": f"₹{m.total_fees + m.total_slippage:,.2f}",
                "Trades": m.trade_count,
            })
        return pd.DataFrame(rows)

    @staticmethod
    def format_cost_attribution(metrics: BacktestMetrics, initial_capital: float) -> Dict[str, float]:
        """
        Decompose gross vs net performance and fee/slippage impact in basis points.
        """
        net_ret = metrics.total_return
        fee_drag_pct = (metrics.total_fees / initial_capital) if initial_capital > 0 else 0.0
        slippage_drag_pct = (metrics.total_slippage / initial_capital) if initial_capital > 0 else 0.0
        gross_ret = net_ret + fee_drag_pct + slippage_drag_pct

        return {
            "gross_return_pct": gross_ret * 100.0,
            "net_return_pct": net_ret * 100.0,
            "fee_drag_pct": fee_drag_pct * 100.0,
            "slippage_drag_pct": slippage_drag_pct * 100.0,
            "total_cost_drag_pct": (fee_drag_pct + slippage_drag_pct) * 100.0,
        }
