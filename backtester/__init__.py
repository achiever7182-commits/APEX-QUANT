"""
backtester/__init__.py — Backtesting engine package.
"""
from backtester.engine import BacktestEngine, BacktestResult
from backtester.metrics import compute_metrics
from backtester.report import print_report

__all__ = ["BacktestEngine", "BacktestResult", "compute_metrics", "print_report"]
