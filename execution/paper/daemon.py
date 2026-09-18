"""
execution/paper/daemon.py — Autonomous Paper Trading Daemon & Endurance Soak Subsystem.

Provides:
  1. Autonomous long-running daemon execution in WALL_CLOCK or ACCELERATED modes.
  2. Fail-closed live trading boundary (Paper-only, zero live broker orders, zero real money).
  3. Graceful cooperative signal handling (SIGINT, SIGTERM) with atomic state flushes.
  4. Periodic atomic process heartbeat emission (data/paper/daemon_heartbeat.json).
  5. Crash-restart recovery restoring account, positions, orders, and idempotency keys.
  6. High-density endurance soak runner auditing accounting and reconciliation invariants.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union
import pandas as pd

from data.market.calendar import NSEMarketCalendar
from execution.exceptions import LiveTradingDisabledError
from execution.models import (
    PaperAccount,
    PaperPosition,
    ReconciliationReport,
    ReconciliationStatus,
)
from execution.paper.models import CycleResult, CycleState
from execution.paper.orchestrator import PaperTradingOrchestrator
from execution.paper.session_models import SessionRecord, SessionState
from execution.paper.telemetry import PaperOperationalTelemetry, get_global_paper_telemetry

logger = logging.getLogger("apex_quant.paper.daemon")


class DaemonMode(str, Enum):
    """Execution timing modes for the paper trading daemon."""
    WALL_CLOCK = "WALL_CLOCK"        # Synchronized to real-world clock and NSE market hours
    ACCELERATED = "ACCELERATED"      # Fast-forward simulated clock for soak & endurance testing


class DaemonStatus(str, Enum):
    """Operational status of the paper trading daemon."""
    INITIALIZING = "INITIALIZING"
    IDLE = "IDLE"
    RUNNING_CYCLE = "RUNNING_CYCLE"
    SLEEPING = "SLEEPING"
    SHUTTING_DOWN = "SHUTTING_DOWN"
    STOPPED = "STOPPED"
    FAILED = "FAILED"


DEFAULT_BENCHMARK_QUOTES: Dict[str, float] = {
    "RELIANCE": 2950.0,
    "TCS": 4150.0,
    "INFY": 1850.0,
    "HDFCBANK": 1650.0,
    "ICICIBANK": 1250.0,
}


@dataclass
class DaemonConfig:
    """Configuration parameters for the paper trading daemon."""
    mode: DaemonMode = DaemonMode.ACCELERATED
    cycle_interval_seconds: float = 60.0
    heartbeat_interval_seconds: float = 5.0
    max_cycles: Optional[int] = None
    symbols: List[str] = field(default_factory=lambda: ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"])
    initial_capital: float = 1_000_000.0
    data_dir: str = "data/paper"
    auto_load_state: bool = True
    force_market_open: bool = False
    rate_limit_delay: float = 0.0
    override_quotes: Optional[Dict[str, float]] = None
    override_volumes: Optional[Dict[str, float]] = None


@dataclass
class HeartbeatData:
    """Structured telemetry data emitted periodically by the daemon."""
    pid: int
    status: str
    mode: str
    uptime_seconds: float
    timestamp: str
    cycles_completed: int
    current_session_id: Optional[str]
    equity: float
    cash: float
    positions_count: int
    last_reconciliation: str
    memory_rss_mb: float
    last_error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SoakReport:
    """Comprehensive summary report produced after an endurance soak test."""
    total_cycles_requested: int
    cycles_completed: int
    elapsed_seconds: float
    initial_equity: float
    final_equity: float
    total_return_pct: float
    orders_generated: int
    orders_filled: int
    orders_rejected: int
    cash_invariant_passed: bool
    position_invariant_passed: bool
    equity_identity_passed: bool
    reconciliation_invariant_passed: bool
    all_invariants_passed: bool
    audit_messages: List[str] = field(default_factory=list)


class PaperTradingDaemon:
    """
    Autonomous paper trading daemon service for Indian equities.
    
    Guarantees:
    - Strict fail-closed paper boundary: raises LiveTradingDisabledError on live attempts.
    - Zero real money risk.
    - Cooperative, atomic signal handling with full state serialization.
    - Zero interference with legacy Binance runners.
    """

    def __init__(
        self,
        config: Optional[DaemonConfig] = None,
        orchestrator: Optional[PaperTradingOrchestrator] = None,
    ) -> None:
        self.config: DaemonConfig = config or DaemonConfig()
        self.data_dir: Path = Path(self.config.data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.heartbeat_file: Path = self.data_dir / "daemon_heartbeat.json"

        self.telemetry: PaperOperationalTelemetry = get_global_paper_telemetry()
        self.status: DaemonStatus = DaemonStatus.INITIALIZING
        self._stop_requested: threading.Event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None
        self._cycle_lock: threading.Lock = threading.Lock()

        self.start_time: float = time.time()
        self.cycles_completed: int = 0
        self.last_error: Optional[str] = None
        self.last_reconciliation_status: str = "N/A"
        self.current_session_id: str = f"session_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

        # Initialize orchestrator with fail-closed checks
        self.orchestrator: PaperTradingOrchestrator = orchestrator or PaperTradingOrchestrator(
            initial_capital=self.config.initial_capital,
            data_dir=str(self.data_dir),
            auto_load_state=self.config.auto_load_state,
        )

        # Enforce strict fail-closed boundary
        if getattr(self.orchestrator.broker, "supports_live_orders", False):
            raise LiveTradingDisabledError("PaperTradingDaemon strictly prohibits live execution brokers.")

        # Register cooperative OS signals
        self._register_signals()

        self.status = DaemonStatus.IDLE
        self._emit_heartbeat()
        logger.info(f"PaperTradingDaemon initialized in {self.config.mode.value} mode. PID: {os.getpid()}")

    def _register_signals(self) -> None:
        """Register graceful signal handlers for SIGINT and SIGTERM."""
        try:
            signal.signal(signal.SIGINT, self._handle_signal)
            if hasattr(signal, "SIGTERM"):
                signal.signal(signal.SIGTERM, self._handle_signal)
        except (ValueError, AttributeError) as exc:
            # Not running in main thread (e.g. invoked in a worker thread in unit tests)
            logger.debug(f"Signal registration skipped (non-main thread): {exc}")

    def _handle_signal(self, signum: int, frame: Any) -> None:
        """Handle OS termination signal with graceful cooperative shutdown."""
        sig_name = signal.Signals(signum).name if hasattr(signal, "Signals") else str(signum)
        logger.warning(f"Caught signal {sig_name}. Initiating graceful paper daemon shutdown...")
        self.request_stop()

    def request_stop(self) -> None:
        """Cooperatively request daemon to stop after current cycle completes."""
        self._stop_requested.set()

    def _emit_heartbeat(self) -> None:
        """Write atomic heartbeat state to disk."""
        try:
            account = self.orchestrator.broker.get_account()
            positions = self.orchestrator.broker.get_positions()
            rss_mb = 0.0
            try:
                import psutil
                rss_mb = psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)
            except Exception:
                pass

            data = HeartbeatData(
                pid=os.getpid(),
                status=self.status.value,
                mode=self.config.mode.value,
                uptime_seconds=time.time() - self.start_time,
                timestamp=datetime.now(timezone.utc).isoformat(),
                cycles_completed=self.cycles_completed,
                current_session_id=self.current_session_id,
                equity=account.total_equity,
                cash=account.cash,
                positions_count=len(positions),
                last_reconciliation=self.last_reconciliation_status,
                memory_rss_mb=round(rss_mb, 2),
                last_error=self.last_error,
            )

            dir_name = self.heartbeat_file.parent
            with tempfile.NamedTemporaryFile("w", dir=dir_name, delete=False, encoding="utf-8") as tf:
                json.dump(data.to_dict(), tf, indent=2)
                temp_name = tf.name
            os.replace(temp_name, str(self.heartbeat_file.resolve()))
        except Exception as exc:
            logger.debug(f"Heartbeat write exception: {exc}")

    def _get_fallback_quotes(self) -> Dict[str, float]:
        """Fetch fallback benchmark prices from local parquet storage or defaults."""
        from data.market.storage import ParquetMarketDataStorage
        quotes: Dict[str, float] = {}
        storage = ParquetMarketDataStorage()
        for s in self.config.symbols:
            try:
                df = storage.read(s, is_adjusted=True)
                if not df.empty and "close" in df.columns:
                    quotes[s] = float(df["close"].iloc[-1])
                    continue
            except Exception:
                pass
            quotes[s] = DEFAULT_BENCHMARK_QUOTES.get(s, 1000.0)
        return quotes

    def run_single_cycle(
        self,
        as_of_time: Optional[datetime] = None,
        candidate_panel: Optional[pd.DataFrame] = None,
        override_quotes: Optional[Dict[str, float]] = None,
        override_volumes: Optional[Dict[str, float]] = None,
    ) -> CycleResult:
        """
        Execute a single rebalance cycle atomically under lock.
        """
        with self._cycle_lock:
            self.status = DaemonStatus.RUNNING_CYCLE
            self._emit_heartbeat()

            force_open = self.config.force_market_open or (self.config.mode == DaemonMode.ACCELERATED)

            # Resolve effective cycle execution timestamp
            cycle_time = as_of_time
            if cycle_time is None:
                if self.config.mode == DaemonMode.ACCELERATED or self.config.force_market_open:
                    ist = timezone(timedelta(hours=5, minutes=30))
                    # Monday 10:00 AM IST (verified open NSE regular trading session)
                    base_dt = datetime(2024, 4, 15, 10, 0, 0, tzinfo=ist)
                    cycle_time = base_dt + timedelta(minutes=self.cycles_completed)

            # Resolve quotes: passed > config > cache > storage fallback
            quotes = override_quotes
            if quotes is None:
                if self.config.override_quotes:
                    quotes = self.config.override_quotes
                else:
                    has_cached = any(self.orchestrator.quote_cache.get_latest(s) is not None for s in self.config.symbols)
                    if not has_cached:
                        quotes = self._get_fallback_quotes()

            vols = override_volumes or self.config.override_volumes

            try:
                result = self.orchestrator.run_cycle(
                    universe=self.config.symbols,
                    as_of_time=cycle_time,
                    candidate_panel=candidate_panel,
                    override_quotes=quotes,
                    override_volumes=vols,
                    force_market_open=force_open,
                )
                self.cycles_completed += 1
                if self.orchestrator._latest_reconciliation:
                    self.last_reconciliation_status = self.orchestrator._latest_reconciliation.status.value
                elif result.reconciliation_report:
                    self.last_reconciliation_status = str(result.reconciliation_report.get("status", "N/A"))

                logger.info(
                    f"Cycle {self.cycles_completed} completed: status={result.state.value}, "
                    f"orders={len(result.orders_generated)}, fills={len(result.fills)}"
                )
                return result
            except Exception as exc:
                self.last_error = str(exc)
                logger.error(f"Error during cycle execution: {exc}")
                raise
            finally:
                self.status = DaemonStatus.IDLE
                self._emit_heartbeat()

    def start(self, blocking: bool = False) -> None:
        """
        Start the daemon loop.
        
        Args:
            blocking: If True, blocks on the main loop. If False, runs in a background thread.
        """
        if self._worker_thread is not None and self._worker_thread.is_alive():
            logger.warning("PaperTradingDaemon is already running.")
            return

        self._stop_requested.clear()
        if blocking:
            self._daemon_loop()
        else:
            self._worker_thread = threading.Thread(target=self._daemon_loop, name="PaperDaemonThread", daemon=True)
            self._worker_thread.start()
            logger.info("PaperTradingDaemon background thread started.")

    def stop(self, timeout: float = 10.0) -> None:
        """
        Gracefully stop the daemon, flushing state and auditing reconciliation.
        """
        logger.info("Stopping PaperTradingDaemon gracefully...")
        self.status = DaemonStatus.SHUTTING_DOWN
        self.request_stop()

        if self._worker_thread is not None and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=timeout)

        # Final state flush and reconciliation audit
        with self._cycle_lock:
            try:
                recon = self.orchestrator.reconcile_state()
                self.last_reconciliation_status = recon.status.value
            except Exception as e:
                logger.error(f"Error during shutdown reconciliation: {e}")

            # Persist full state
            account = self.orchestrator.broker.get_account()
            positions = self.orchestrator.broker.get_positions()
            orders = getattr(self.orchestrator.order_manager, "orders", {})
            fills = self.orchestrator.broker.get_fills()
            self.orchestrator.persistence.save_state(account, positions, orders, fills)

        self.status = DaemonStatus.STOPPED
        self._emit_heartbeat()
        logger.info("PaperTradingDaemon cleanly stopped and state flushed.")

    def _daemon_loop(self) -> None:
        """Main operational execution loop."""
        logger.info(f"Starting daemon loop ({self.config.mode.value})...")
        last_heartbeat_t = time.time()

        while not self._stop_requested.is_set():
            now = time.time()

            # Heartbeat check
            if now - last_heartbeat_t >= self.config.heartbeat_interval_seconds:
                self._emit_heartbeat()
                last_heartbeat_t = now

            # Check maximum cycles limit (if set)
            if self.config.max_cycles is not None and self.cycles_completed >= self.config.max_cycles:
                logger.info(f"Reached configured max_cycles ({self.config.max_cycles}). Stopping loop.")
                break

            # Execute Cycle
            try:
                self.run_single_cycle()
            except Exception as exc:
                self.last_error = str(exc)
                logger.error(f"Daemon cycle failed: {exc}")

            # Sleeping between cycles
            self.status = DaemonStatus.SLEEPING
            self._emit_heartbeat()

            # Cooperative sleeping with sub-second polling for stop requests
            sleep_duration = self.config.cycle_interval_seconds if self.config.mode == DaemonMode.WALL_CLOCK else 0.05
            sleep_start = time.time()
            while time.time() - sleep_start < sleep_duration:
                if self._stop_requested.is_set():
                    break
                time.sleep(0.05)

        self.status = DaemonStatus.STOPPED
        self._emit_heartbeat()

    def run_soak(
        self,
        num_cycles: int = 25,
        candidate_panel: Optional[pd.DataFrame] = None,
        override_quotes_trajectory: Optional[List[Dict[str, float]]] = None,
    ) -> SoakReport:
        """
        Execute an accelerated multi-cycle endurance soak run, verifying all invariants
        after every cycle.
        """
        logger.info(f"Starting {num_cycles}-cycle endurance soak run...")
        start_t = time.perf_counter()
        initial_account = self.orchestrator.broker.get_account()
        initial_equity = initial_account.total_equity

        cash_invariant = True
        position_invariant = True
        equity_identity = True
        reconciliation_invariant = True
        audit_messages: List[str] = []

        total_orders_gen = 0
        total_orders_filled = 0
        total_orders_rejected = 0

        for cycle_idx in range(num_cycles):
            if self._stop_requested.is_set():
                audit_messages.append(f"Soak interrupted by stop request at cycle {cycle_idx}")
                break

            quotes = None
            if override_quotes_trajectory and cycle_idx < len(override_quotes_trajectory):
                quotes = override_quotes_trajectory[cycle_idx]

            try:
                res = self.run_single_cycle(
                    candidate_panel=candidate_panel,
                    override_quotes=quotes,
                )
                total_orders_gen += len(res.orders_generated)
                total_orders_filled += len(res.fills)
                total_orders_rejected += len(res.orders_rejected)
            except Exception as e:
                audit_messages.append(f"Cycle {cycle_idx} failed: {e}")
                continue

            # Invariant Audits after every cycle:
            account = self.orchestrator.broker.get_account()
            positions = self.orchestrator.broker.get_positions()

            # 1. Cash non-negative
            if account.cash < -1e-5:
                cash_invariant = False
                audit_messages.append(f"Cycle {cycle_idx}: Negative cash violation: ₹{account.cash:,.2f}")

            # 2. No shorting
            for sym, pos in positions.items():
                if pos.shares < -1e-5:
                    position_invariant = False
                    audit_messages.append(f"Cycle {cycle_idx}: Negative shares for {sym}: {pos.shares}")

            # 3. Equity identity
            holdings_val = sum(pos.shares * pos.current_price for pos in positions.values())
            computed_nav = account.cash + holdings_val
            if abs(computed_nav - account.total_equity) > 1.0:
                equity_identity = False
                audit_messages.append(
                    f"Cycle {cycle_idx}: Equity identity mismatch: computed=₹{computed_nav:.2f}, "
                    f"account=₹{account.total_equity:.2f}"
                )

            # 4. Reconciliation audit
            recon = self.orchestrator._latest_reconciliation
            if recon is not None and not recon.is_clean:
                reconciliation_invariant = False
                audit_messages.append(f"Cycle {cycle_idx}: Reconciliation discrepancy: {recon.discrepancies}")

        elapsed = time.perf_counter() - start_t
        final_account = self.orchestrator.broker.get_account()
        final_equity = final_account.total_equity
        ret_pct = ((final_equity - initial_equity) / initial_equity) * 100.0 if initial_equity > 0 else 0.0

        all_passed = (cash_invariant and position_invariant and equity_identity and reconciliation_invariant)
        return SoakReport(
            total_cycles_requested=num_cycles,
            cycles_completed=self.cycles_completed,
            elapsed_seconds=elapsed,
            initial_equity=initial_equity,
            final_equity=final_equity,
            total_return_pct=ret_pct,
            orders_generated=total_orders_gen,
            orders_filled=total_orders_filled,
            orders_rejected=total_orders_rejected,
            cash_invariant_passed=cash_invariant,
            position_invariant_passed=position_invariant,
            equity_identity_passed=equity_identity,
            reconciliation_invariant_passed=reconciliation_invariant,
            all_invariants_passed=all_passed,
            audit_messages=audit_messages,
        )
