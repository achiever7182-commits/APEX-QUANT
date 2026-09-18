"""
paper — Unified Paper Trading Facade for APEX-QUANT.
"""

from execution.paper.models import (
    CycleResult,
    CycleState,
    PortfolioDecision,
    SignalSnapshot,
)
from execution.paper.orchestrator import (
    PaperTradingOrchestrator,
    get_global_paper_orchestrator,
)

__all__ = [
    "CycleResult",
    "CycleState",
    "PortfolioDecision",
    "SignalSnapshot",
    "PaperTradingOrchestrator",
    "get_global_paper_orchestrator",
]
