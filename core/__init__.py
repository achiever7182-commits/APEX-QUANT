"""
core — Strategy engine, risk management, and shared trading primitives.

Public API:
    Signal, MarketData, Strategy, SMACrossoverStrategy   (strategy.py)
    TickMomentumStrategy                                  (tick_strategy.py)
    RiskManager, RiskConfig                               (risk_manager.py)
    get_strategy, list_strategies                         (strategies/)
"""

from core.strategy import Signal, MarketData, Strategy, SMACrossoverStrategy
from core.tick_strategy import TickMomentumStrategy
from core.risk_manager import RiskManager, RiskConfig
from core.strategies import get_strategy, list_strategies

__all__ = [
    "Signal",
    "MarketData",
    "Strategy",
    "SMACrossoverStrategy",
    "TickMomentumStrategy",
    "RiskManager",
    "RiskConfig",
    "get_strategy",
    "list_strategies",
]
