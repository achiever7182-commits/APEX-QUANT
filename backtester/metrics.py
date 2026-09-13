"""
backtester/metrics.py — Performance metric calculations.

Computes the standard suite of metrics used by professional quant traders
to evaluate whether a strategy has a real edge:

  - Total return
  - Sharpe ratio (risk-adjusted return, higher is better, > 1.0 is acceptable)
  - Max drawdown (largest peak-to-trough equity drop, the "pain" metric)
  - Win rate
  - Profit factor (gross profit / gross loss, > 1.5 is acceptable)
  - CAGR (annualized return)
  - Average win / average loss
  - Expectancy (expected $ profit per trade)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from backtester.engine import BacktestResult, Trade


@dataclass
class Metrics:
    total_return_pct: float
    total_pnl: float
    sharpe_ratio: float
    max_drawdown_pct: float
    win_rate_pct: float
    profit_factor: float
    cagr_pct: float
    trade_count: int
    win_count: int
    loss_count: int
    avg_win: float
    avg_loss: float
    expectancy: float
    total_fees: float
    candle_count: int


TIMEFRAME_BARS_PER_YEAR: dict[str, int] = {
    "1m": 525_600,
    "3m": 175_200,
    "5m": 105_120,
    "15m": 35_040,
    "30m": 17_520,
    "1h": 8_760,
    "2h": 4_380,
    "4h": 2_190,
    "6h": 1_460,
    "8h": 1_095,
    "12h": 730,
    "1d": 365,
    "3d": 122,
    "1w": 52,
}


def compute_metrics(result: BacktestResult) -> Metrics:
    trades = result.trades
    equity = result.equity_curve
    timestamps = result.candle_timestamps
    timeframe = getattr(result, "timeframe", "1h") or "1h"

    total_pnl = result.final_balance - result.starting_balance
    total_return_pct = (total_pnl / result.starting_balance) * 100.0

    # Win / loss split
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl < 0]
    win_count = len(wins)
    loss_count = len(losses)
    win_rate = (win_count / len(trades) * 100.0) if trades else 0.0

    avg_win = (sum(t.pnl for t in wins) / win_count) if wins else 0.0
    avg_loss = (sum(t.pnl for t in losses) / loss_count) if losses else 0.0

    gross_profit = sum(t.pnl for t in wins)
    gross_loss = abs(sum(t.pnl for t in losses))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")

    expectancy = (total_pnl / len(trades)) if trades else 0.0

    total_fees = sum(t.fee for t in trades)

    # Max drawdown from equity curve
    max_drawdown_pct = _max_drawdown(equity)

    # Sharpe ratio: daily-resampled when timestamps available, else timeframe-adjusted
    sharpe = _sharpe(equity, timestamps=timestamps, timeframe=timeframe)

    # CAGR: timestamp-based from actual candle range, else timeframe-adjusted count
    cagr = _cagr(
        start=result.starting_balance,
        end=result.final_balance,
        timestamps=timestamps,
        candles=result.candle_count,
        timeframe=timeframe,
    )

    return Metrics(
        total_return_pct=round(total_return_pct, 4),
        total_pnl=round(total_pnl, 4),
        sharpe_ratio=round(sharpe, 4),
        max_drawdown_pct=round(max_drawdown_pct, 4),
        win_rate_pct=round(win_rate, 2),
        profit_factor=round(profit_factor, 4),
        cagr_pct=round(cagr, 4),
        trade_count=len(trades),
        win_count=win_count,
        loss_count=loss_count,
        avg_win=round(avg_win, 4),
        avg_loss=round(avg_loss, 4),
        expectancy=round(expectancy, 4),
        total_fees=round(total_fees, 4),
        candle_count=result.candle_count,
    )


def _max_drawdown(equity: list[float]) -> float:
    if not equity:
        return 0.0
    peak = equity[0]
    max_dd = 0.0
    for value in equity:
        if value > peak:
            peak = value
        dd = (peak - value) / peak * 100.0 if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd
    return max_dd


def _sharpe(
    equity: list[float],
    timestamps: list[int] | None = None,
    timeframe: str = "1h",
    risk_free_rate: float = 0.0,
) -> float:
    """
    Sharpe ratio from the equity curve.

    Prefers daily-resampled returns annualized with sqrt(365) to eliminate
    zero-padding distortion from flat/cash periods.
    Falls back to bar-level returns annualized by the timeframe's annual factor.
    """
    if isinstance(timestamps, (int, float)):
        risk_free_rate = float(timestamps)
        timestamps = None

    if len(equity) < 2:
        return 0.0

    # 1. Daily-resampled Sharpe (preferred when timestamps are available)
    if timestamps and len(timestamps) == len(equity) and len(timestamps) >= 2:
        daily_equity: dict[int, float] = {}
        for ts, eq in zip(timestamps, equity):
            day_idx = ts // (86_400 * 1000)
            daily_equity[day_idx] = eq

        sorted_days = sorted(daily_equity.keys())
        if len(sorted_days) >= 2:
            daily_values = [daily_equity[d] for d in sorted_days]
            daily_returns = [
                (daily_values[i] - daily_values[i - 1]) / daily_values[i - 1]
                for i in range(1, len(daily_values))
                if daily_values[i - 1] > 0
            ]
            n = len(daily_returns)
            if n >= 2:
                mean = sum(daily_returns) / n
                variance = sum((r - mean) ** 2 for r in daily_returns) / (n - 1)
                std = math.sqrt(variance) if variance > 0 else 0.0
                if std > 0:
                    return (mean - (risk_free_rate / 365.0)) / std * math.sqrt(365.0)
                return 0.0

    # 2. Fallback: bar-level Sharpe with dynamic timeframe annualization
    returns = [(equity[i] - equity[i - 1]) / equity[i - 1] for i in range(1, len(equity))]
    n = len(returns)
    if n < 2:
        return 0.0
    mean = sum(returns) / n
    variance = sum((r - mean) ** 2 for r in returns) / (n - 1)
    std = math.sqrt(variance) if variance > 0 else 0.0
    if std == 0:
        return 0.0

    bars_per_year = TIMEFRAME_BARS_PER_YEAR.get(timeframe.lower(), 525_600)
    annual_factor = math.sqrt(bars_per_year)
    return (mean - risk_free_rate / bars_per_year) / std * annual_factor


def _cagr(
    start: float,
    end: float,
    timestamps: list[int] | None = None,
    candles: int = 0,
    timeframe: str = "1h",
) -> float:
    """
    Compound Annual Growth Rate (CAGR).

    Prefers actual candle timestamps (ms):
        years = (timestamps[-1] - timestamps[0]) / (365.25 * 86400 * 1000)
    Falls back to candle-count estimation with dynamic timeframe bars/year:
        years = candles / bars_per_year
    """
    if isinstance(timestamps, (int, float)):
        candles = int(timestamps)
        timestamps = None

    if start <= 0 or end <= 0:
        return 0.0

    years = 0.0
    if timestamps and len(timestamps) >= 2:
        duration_ms = timestamps[-1] - timestamps[0]
        if duration_ms > 0:
            years = duration_ms / (365.25 * 86_400.0 * 1000.0)

    if years <= 0.0 and candles > 0:
        bars_per_year = TIMEFRAME_BARS_PER_YEAR.get(timeframe.lower(), 525_600)
        years = candles / float(bars_per_year)

    if years <= 0.0:
        return 0.0

    return ((end / start) ** (1.0 / years) - 1.0) * 100.0
