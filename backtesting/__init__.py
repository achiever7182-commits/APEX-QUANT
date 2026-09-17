"""
backtesting package — APEX-QUANT Full Portfolio Backtesting Subsystem.

Provides event-driven chronological simulation, point-in-time safety,
realistic execution friction, double-entry accounting, and performance analytics.
"""
from __future__ import annotations

from backtesting.config import BacktestConfig
from backtesting.models import (
    OrderSide,
    OrderStatus,
    SimulatedOrder,
    SimulatedFill,
    HoldingPosition,
    PortfolioSnapshot,
    BacktestMetrics,
    WalkForwardPeriodResult,
    BacktestResult,
)
from backtesting.timeline import BacktestTimeline
from backtesting.data_feed import PointInTimeDataFeed
from backtesting.signal_runner import SignalRunner
from backtesting.portfolio_runner import PortfolioRunner
from backtesting.execution_simulator import ExecutionSimulator
from backtesting.accounting import PortfolioAccounting
from backtesting.benchmarks import BenchmarkEngine
from backtesting.performance import PerformanceAnalyzer
from backtesting.walk_forward import WalkForwardAnalyzer, WalkForwardMLTrainer, WalkForwardTrainAuditLog
from backtesting.diagnostics import BacktestDiagnostics
from backtesting.engine import BacktestEngine

__all__ = [
    "BacktestConfig",
    "OrderSide",
    "OrderStatus",
    "SimulatedOrder",
    "SimulatedFill",
    "HoldingPosition",
    "PortfolioSnapshot",
    "BacktestMetrics",
    "WalkForwardPeriodResult",
    "BacktestResult",
    "BacktestTimeline",
    "PointInTimeDataFeed",
    "SignalRunner",
    "PortfolioRunner",
    "ExecutionSimulator",
    "PortfolioAccounting",
    "BenchmarkEngine",
    "PerformanceAnalyzer",
    "WalkForwardAnalyzer",
    "WalkForwardMLTrainer",
    "WalkForwardTrainAuditLog",
    "BacktestDiagnostics",
    "BacktestEngine",
]
