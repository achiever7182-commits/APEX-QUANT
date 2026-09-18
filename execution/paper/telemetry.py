"""
execution/paper/telemetry.py — Operational Telemetry & Health Tracker for Extended Paper Trading.

Tracks all 19 mandatory operational reliability metrics:
  - sessions_started, sessions_completed, sessions_failed
  - cycles_started, cycles_completed
  - orders_generated, orders_filled, orders_rejected
  - duplicate_orders, risk_rejections
  - data_errors, model_errors, execution_errors, reconciliation_errors
  - restart_recoveries
  - average_cycle_latency, maximum_cycle_latency
  - symbols_processed, symbols_rejected

Along with active session context:
  - current_session, current_cycle, current_state
  - last_successful_cycle, last_error, last_reconciliation_status
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional


class PaperOperationalTelemetry:
    """Thread-safe collector for extended paper trading operational reliability telemetry."""

    def __init__(self):
        self._lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        """Reset all metrics to initial state."""
        with self._lock:
            # 1. Sessions
            self.sessions_started: int = 0
            self.sessions_completed: int = 0
            self.sessions_failed: int = 0

            # 2. Cycles
            self.cycles_started: int = 0
            self.cycles_completed: int = 0

            # 3. Orders & Fills
            self.orders_generated: int = 0
            self.orders_filled: int = 0
            self.orders_rejected: int = 0
            self.duplicate_orders: int = 0
            self.risk_rejections: int = 0

            # 4. Errors & Failures
            self.data_errors: int = 0
            self.model_errors: int = 0
            self.execution_errors: int = 0
            self.reconciliation_errors: int = 0

            # 5. Recovery & Latency
            self.restart_recoveries: int = 0
            self._cycle_latencies: List[float] = []
            self.average_cycle_latency: float = 0.0
            self.maximum_cycle_latency: float = 0.0

            # 6. Symbols
            self.symbols_processed: int = 0
            self.symbols_rejected: int = 0

            # 7. Current Operational State Context
            self.current_session: Optional[str] = None
            self.current_cycle: Optional[str] = None
            self.current_state: str = "IDLE"
            self.last_successful_cycle: Optional[str] = None
            self.last_error: Optional[str] = None
            self.last_reconciliation_status: Optional[str] = None

    def record_session_start(self, session_id: str) -> None:
        with self._lock:
            self.sessions_started += 1
            self.current_session = session_id
            self.current_state = "RUNNING"

    def record_session_completed(self, session_id: str) -> None:
        with self._lock:
            self.sessions_completed += 1
            if self.current_session == session_id:
                self.current_state = "COMPLETED"

    def record_session_failed(self, session_id: str, error: str) -> None:
        with self._lock:
            self.sessions_failed += 1
            self.last_error = str(error)
            if self.current_session == session_id:
                self.current_state = "FAILED"

    def record_cycle_start(self, cycle_id: str) -> None:
        with self._lock:
            self.cycles_started += 1
            self.current_cycle = cycle_id

    def record_cycle_completed(self, cycle_id: str, duration_ms: float) -> None:
        with self._lock:
            self.cycles_completed += 1
            self.last_successful_cycle = cycle_id
            self._cycle_latencies.append(float(duration_ms))
            self.average_cycle_latency = round(sum(self._cycle_latencies) / len(self._cycle_latencies), 2)
            if duration_ms > self.maximum_cycle_latency:
                self.maximum_cycle_latency = round(float(duration_ms), 2)

    def record_orders(
        self,
        generated: int = 0,
        filled: int = 0,
        rejected: int = 0,
        duplicates: int = 0,
        risk_rejections: int = 0,
    ) -> None:
        with self._lock:
            self.orders_generated += generated
            self.orders_filled += filled
            self.orders_rejected += rejected
            self.duplicate_orders += duplicates
            self.risk_rejections += risk_rejections

    def record_symbols(self, processed: int = 0, rejected: int = 0) -> None:
        with self._lock:
            self.symbols_processed += processed
            self.symbols_rejected += rejected

    def record_data_error(self, message: Optional[str] = None) -> None:
        with self._lock:
            self.data_errors += 1
            if message:
                self.last_error = message

    def record_model_error(self, message: Optional[str] = None) -> None:
        with self._lock:
            self.model_errors += 1
            if message:
                self.last_error = message

    def record_execution_error(self, message: Optional[str] = None) -> None:
        with self._lock:
            self.execution_errors += 1
            if message:
                self.last_error = message

    def record_reconciliation(self, status: str, has_error: bool = False) -> None:
        with self._lock:
            self.last_reconciliation_status = status
            if has_error:
                self.reconciliation_errors += 1

    def record_restart_recovery(self) -> None:
        with self._lock:
            self.restart_recoveries += 1

    def set_operational_state(self, state: str) -> None:
        with self._lock:
            self.current_state = state

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            return {
                # 19 Mandatory Operational Reliability Metrics
                "sessions_started": self.sessions_started,
                "sessions_completed": self.sessions_completed,
                "sessions_failed": self.sessions_failed,
                "cycles_started": self.cycles_started,
                "cycles_completed": self.cycles_completed,
                "orders_generated": self.orders_generated,
                "orders_filled": self.orders_filled,
                "orders_rejected": self.orders_rejected,
                "duplicate_orders": self.duplicate_orders,
                "risk_rejections": self.risk_rejections,
                "data_errors": self.data_errors,
                "model_errors": self.model_errors,
                "execution_errors": self.execution_errors,
                "reconciliation_errors": self.reconciliation_errors,
                "restart_recoveries": self.restart_recoveries,
                "average_cycle_latency": self.average_cycle_latency,
                "maximum_cycle_latency": self.maximum_cycle_latency,
                "symbols_processed": self.symbols_processed,
                "symbols_rejected": self.symbols_rejected,

                # Operational State Context
                "current_session": self.current_session,
                "current_cycle": self.current_cycle,
                "current_state": self.current_state,
                "last_successful_cycle": self.last_successful_cycle,
                "last_error": self.last_error,
                "last_reconciliation_status": self.last_reconciliation_status,
            }

    def load_from_dict(self, d: Dict[str, Any]) -> None:
        with self._lock:
            self.sessions_started = int(d.get("sessions_started", 0))
            self.sessions_completed = int(d.get("sessions_completed", 0))
            self.sessions_failed = int(d.get("sessions_failed", 0))
            self.cycles_started = int(d.get("cycles_started", 0))
            self.cycles_completed = int(d.get("cycles_completed", 0))
            self.orders_generated = int(d.get("orders_generated", 0))
            self.orders_filled = int(d.get("orders_filled", 0))
            self.orders_rejected = int(d.get("orders_rejected", 0))
            self.duplicate_orders = int(d.get("duplicate_orders", 0))
            self.risk_rejections = int(d.get("risk_rejections", 0))
            self.data_errors = int(d.get("data_errors", 0))
            self.model_errors = int(d.get("model_errors", 0))
            self.execution_errors = int(d.get("execution_errors", 0))
            self.reconciliation_errors = int(d.get("reconciliation_errors", 0))
            self.restart_recoveries = int(d.get("restart_recoveries", 0))
            self.average_cycle_latency = float(d.get("average_cycle_latency", 0.0))
            self.maximum_cycle_latency = float(d.get("maximum_cycle_latency", 0.0))
            self.symbols_processed = int(d.get("symbols_processed", 0))
            self.symbols_rejected = int(d.get("symbols_rejected", 0))

            self.current_session = d.get("current_session")
            self.current_cycle = d.get("current_cycle")
            self.current_state = str(d.get("current_state", "IDLE"))
            self.last_successful_cycle = d.get("last_successful_cycle")
            self.last_error = d.get("last_error")
            self.last_reconciliation_status = d.get("last_reconciliation_status")


# Global singleton telemetry instance
_global_telemetry: Optional[PaperOperationalTelemetry] = None
_telemetry_lock = threading.Lock()


def get_global_paper_telemetry() -> PaperOperationalTelemetry:
    """Return the global singleton PaperOperationalTelemetry instance."""
    global _global_telemetry
    with _telemetry_lock:
        if _global_telemetry is None:
            _global_telemetry = PaperOperationalTelemetry()
        return _global_telemetry
