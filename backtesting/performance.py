"""
backtesting/performance.py — Realized performance and risk metric calculation.

Computes CAGR, Sharpe, Sortino, Drawdown, Calmar, Turnover, and Cost metrics.
Strictly separates realized empirical performance from model-expected returns.
"""
from __future__ import annotations

from typing import List
import numpy as np
import pandas as pd

from backtesting.models import BacktestMetrics, PortfolioSnapshot, SimulatedFill


class PerformanceAnalyzer:
    """
    Computes rigorous quantitative portfolio performance and risk statistics.
    """

    @staticmethod
    def evaluate_performance(
        snapshots: List[PortfolioSnapshot],
        fills: List[SimulatedFill],
        initial_capital: float = 1_000_000.0,
        risk_free_rate: float = 0.065,
        cagr_convention: str = "trading",
    ) -> BacktestMetrics:
        """
        Evaluate full portfolio performance from daily snapshots and fill records.

        Parameters:
            snapshots: Daily PortfolioSnapshot series.
            fills: Executed SimulatedFill records.
            initial_capital: Starting capital.
            risk_free_rate: Annualized risk-free rate (default 6.5% for Indian equities).
            cagr_convention: 'trading' (252 trading sessions/year) or 'calendar' (365.25 days/year).
        """
        if not snapshots:
            return BacktestMetrics(
                total_return=0.0,
                annualized_return=0.0,
                cagr=0.0,
                annualized_volatility=0.0,
                sharpe_ratio=0.0,
                sortino_ratio=0.0,
                max_drawdown=0.0,
                max_drawdown_duration_days=0,
                calmar_ratio=0.0,
                win_rate=0.0,
                profit_factor=0.0,
                total_turnover=0.0,
                total_fees=0.0,
                total_slippage=0.0,
                rebalance_count=0,
                trade_count=0,
                average_positions=0.0,
                average_cash_weight=1.0,
                average_turnover=0.0,
                annualized_turnover=0.0,
                calendar_cagr=0.0,
            )

        n_bars = len(snapshots)
        final_equity = snapshots[-1].portfolio_value
        total_return = (final_equity - initial_capital) / initial_capital if initial_capital > 0 else 0.0

        # Daily returns series
        daily_rets = np.array([s.daily_return for s in snapshots[1:]], dtype=float) if n_bars > 1 else np.array([0.0])

        # CAGR calculations
        # 1. Trading-day convention (252 market sessions/year)
        years_trading = n_bars / 252.0 if n_bars > 0 else 1.0
        if years_trading > 0 and (1.0 + total_return) > 0:
            cagr_trading = ((1.0 + total_return) ** (1.0 / years_trading)) - 1.0
        else:
            cagr_trading = 0.0

        # 2. Calendar-day convention (365.25 days/year)
        if n_bars > 1:
            start_dt = pd.to_datetime(snapshots[0].timestamp)
            end_dt = pd.to_datetime(snapshots[-1].timestamp)
            cal_days = max(1, (end_dt - start_dt).days)
            years_cal = cal_days / 365.25
            cagr_cal = ((1.0 + total_return) ** (1.0 / years_cal)) - 1.0 if (1.0 + total_return) > 0 else 0.0
        else:
            cagr_cal = cagr_trading

        cagr = cagr_trading if cagr_convention == "trading" else cagr_cal
        ann_return = np.mean(daily_rets) * 252.0 if len(daily_rets) > 0 else 0.0

        # Volatility
        daily_std = np.std(daily_rets, ddof=1) if len(daily_rets) > 1 else 0.0
        ann_vol = daily_std * np.sqrt(252.0)

        # Sharpe Ratio (with configurable risk-free rate)
        excess_return = ann_return - risk_free_rate
        if ann_vol > 1e-6:
            sharpe = excess_return / ann_vol
        else:
            sharpe = 0.0

        # Standard Sortino Ratio (full-sample lower partial moment)
        target_daily = risk_free_rate / 252.0
        downside_diffs = np.minimum(0.0, daily_rets - target_daily)
        if len(downside_diffs) > 1:
            downside_variance = np.mean(downside_diffs ** 2)
            downside_std = np.sqrt(downside_variance) * np.sqrt(252.0)
            sortino = (excess_return / downside_std) if downside_std > 1e-6 else 0.0
        else:
            sortino = sharpe

        # Max Drawdown and Drawdown Duration
        drawdowns = np.array([s.drawdown for s in snapshots], dtype=float)
        max_dd = float(np.max(drawdowns)) if len(drawdowns) > 0 else 0.0

        # Drawdown duration
        max_dd_duration = 0
        current_duration = 0
        for dd in drawdowns:
            if dd > 1e-4:
                current_duration += 1
                if current_duration > max_dd_duration:
                    max_dd_duration = current_duration
            else:
                current_duration = 0

        # Calmar Ratio
        calmar = (cagr / max_dd) if max_dd > 1e-6 else 0.0

        # Win Rate (% positive return days)
        win_days = np.sum(daily_rets > 0)
        win_rate = (win_days / len(daily_rets)) if len(daily_rets) > 0 else 0.0

        # Profit Factor
        gross_gains = np.sum(daily_rets[daily_rets > 0])
        gross_losses = np.abs(np.sum(daily_rets[daily_rets < 0]))
        profit_factor = (gross_gains / gross_losses) if gross_losses > 1e-6 else (float("inf") if gross_gains > 0 else 0.0)

        # Costs and Turnover Breakdown
        total_fees = snapshots[-1].fees_paid
        total_slippage = snapshots[-1].slippage_paid
        total_turnover = sum(s.turnover for s in snapshots)  # Cumulative one-way turnover
        rebalance_count = sum(1 for s in snapshots if s.is_rebalance_bar)
        avg_turnover = (total_turnover / rebalance_count) if rebalance_count > 0 else 0.0
        ann_turnover = total_turnover * (252.0 / n_bars) if n_bars > 0 else total_turnover
        trade_count = sum(1 for f in fills if f.executed_quantity > 0)

        # Average portfolio characteristics
        avg_positions = float(np.mean([len([p for p in s.positions.values() if p.shares > 0]) for s in snapshots]))
        avg_cash_weight = float(np.mean([s.cash / s.portfolio_value if s.portfolio_value > 0 else 1.0 for s in snapshots]))

        return BacktestMetrics(
            total_return=total_return,
            annualized_return=ann_return,
            cagr=cagr,
            annualized_volatility=ann_vol,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            max_drawdown=max_dd,
            max_drawdown_duration_days=max_dd_duration,
            calmar_ratio=calmar,
            win_rate=win_rate,
            profit_factor=profit_factor,
            total_turnover=total_turnover,
            total_fees=total_fees,
            total_slippage=total_slippage,
            rebalance_count=rebalance_count,
            trade_count=trade_count,
            average_positions=avg_positions,
            average_cash_weight=avg_cash_weight,
            average_turnover=avg_turnover,
            annualized_turnover=ann_turnover,
            calendar_cagr=cagr_cal,
        )

    @staticmethod
    def build_equity_curve_dataframe(snapshots: List[PortfolioSnapshot]) -> pd.DataFrame:
        """Construct full time series DataFrame for visualization and reporting."""
        records = [
            {
                "timestamp": s.timestamp,
                "portfolio_value": s.portfolio_value,
                "cash": s.cash,
                "gross_exposure": s.gross_exposure,
                "daily_return": s.daily_return,
                "cumulative_return": s.cumulative_return,
                "drawdown": s.drawdown,
                "realized_pnl": s.realized_pnl,
                "unrealized_pnl": s.unrealized_pnl,
                "fees_paid": s.fees_paid,
                "slippage_paid": s.slippage_paid,
                "turnover": s.turnover,
                "is_rebalance": s.is_rebalance_bar,
                "position_count": len([p for p in s.positions.values() if p.shares > 0]),
            }
            for s in snapshots
        ]
        df = pd.DataFrame.from_records(records)
        if not df.empty:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df = df.set_index("timestamp")
        return df
