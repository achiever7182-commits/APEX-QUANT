"""
execution/paper — End-to-end Paper Trading Subsystem for Indian Equities.
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
