"""
execution/paper — End-to-end Paper Trading Subsystem for Indian Equities.
"""

from execution.paper.models import (
    CycleResult,
    CycleState,
    InvalidSessionTransitionError,
    MultiSessionConfig,
    PaperPerformanceReport,
    PortfolioDecision,
    SessionRecord,
    SessionState,
    SessionTransitionValidator,
    SignalSnapshot,
)
from execution.paper.orchestrator import (
    PaperTradingOrchestrator,
    get_global_paper_orchestrator,
)
from execution.paper.simulation import (
    MultiSessionSimulationEngine,
    get_global_simulation_engine,
)
from execution.paper.telemetry import (
    PaperOperationalTelemetry,
    get_global_paper_telemetry,
)

__all__ = [
    "CycleResult",
    "CycleState",
    "InvalidSessionTransitionError",
    "MultiSessionConfig",
    "PaperPerformanceReport",
    "PortfolioDecision",
    "SessionRecord",
    "SessionState",
    "SessionTransitionValidator",
    "SignalSnapshot",
    "PaperTradingOrchestrator",
    "get_global_paper_orchestrator",
    "MultiSessionSimulationEngine",
    "get_global_simulation_engine",
    "PaperOperationalTelemetry",
    "get_global_paper_telemetry",
]
