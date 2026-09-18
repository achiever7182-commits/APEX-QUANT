"""
tests/test_step14_daemon_soak.py — Step 14: Autonomous Paper Trading Daemon & Endurance Soak Validation.

Validates:
1. Daemon lifecycle (start, cycle execution, graceful stop).
2. Heartbeat monitoring emission and schema validation.
3. Graceful cooperative shutdown and state flush.
4. Crash-restart recovery with atomic ledger restoration.
5. Fail-closed live trading barrier.
6. 25-cycle endurance soak run validating accounting and reconciliation invariants.
7. CLI runner integration in run.py.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional
import pandas as pd
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from execution.exceptions import LiveTradingDisabledError
from execution.paper.daemon import (
    DaemonConfig,
    DaemonMode,
    DaemonStatus,
    PaperTradingDaemon,
    SoakReport,
)
from execution.paper.orchestrator import PaperTradingOrchestrator
from execution.paper_broker import PaperBroker


@pytest.fixture
def temp_daemon_env():
    """Create isolated temporary directory for paper daemon persistence and heartbeat."""
    temp_dir = Path(tempfile.mkdtemp(prefix="apex_daemon_test_"))
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_daemon_lifecycle_start_stop(temp_daemon_env):
    """Verify daemon starts cleanly, executes in background, and stops gracefully on command."""
    cfg = DaemonConfig(
        mode=DaemonMode.ACCELERATED,
        cycle_interval_seconds=0.05,
        heartbeat_interval_seconds=0.5,
        max_cycles=3,
        data_dir=str(temp_daemon_env),
        initial_capital=500_000.0,
        force_market_open=True,
    )
    daemon = PaperTradingDaemon(config=cfg)
    assert daemon.status == DaemonStatus.IDLE

    # Start non-blocking in background
    daemon.start(blocking=False)
    time.sleep(0.4)

    daemon.stop(timeout=5.0)
    assert daemon.status == DaemonStatus.STOPPED
    assert daemon.cycles_completed >= 1


def test_daemon_heartbeat_emission(temp_daemon_env):
    """Verify daemon emits structured, atomic heartbeat file with valid telemetry."""
    cfg = DaemonConfig(
        mode=DaemonMode.ACCELERATED,
        cycle_interval_seconds=0.1,
        heartbeat_interval_seconds=0.1,
        max_cycles=1,
        data_dir=str(temp_daemon_env),
        force_market_open=True,
    )
    daemon = PaperTradingDaemon(config=cfg)
    daemon.start(blocking=False)
    time.sleep(0.3)
    daemon.stop(timeout=5.0)

    heartbeat_path = temp_daemon_env / "daemon_heartbeat.json"
    assert heartbeat_path.exists(), "Heartbeat JSON file was not emitted."

    with open(heartbeat_path, "r", encoding="utf-8") as f:
        hb = json.load(f)

    assert hb["pid"] == os.getpid()
    assert hb["mode"] == "ACCELERATED"
    assert hb["status"] == "STOPPED"
    assert hb["uptime_seconds"] >= 0.0
    assert "timestamp" in hb
    assert hb["equity"] >= 0.0
    assert hb["cash"] >= 0.0
    assert isinstance(hb["positions_count"], int)


def test_daemon_graceful_stop_request(temp_daemon_env):
    """Verify request_stop cooperatively halts execution loop without corrupting state."""
    cfg = DaemonConfig(
        mode=DaemonMode.ACCELERATED,
        cycle_interval_seconds=0.05,
        heartbeat_interval_seconds=1.0,
        max_cycles=100,
        data_dir=str(temp_daemon_env),
        force_market_open=True,
    )
    daemon = PaperTradingDaemon(config=cfg)
    daemon.start(blocking=False)

    time.sleep(0.2)
    daemon.request_stop()
    daemon.stop(timeout=5.0)

    assert daemon.status == DaemonStatus.STOPPED
    # Verified state was saved to disk
    assert (temp_daemon_env / "account.json").exists()
    assert (temp_daemon_env / "positions.json").exists()


def test_daemon_crash_restart_recovery(temp_daemon_env):
    """Verify second daemon instance restores account, positions, and reconciliation from disk."""
    cfg = DaemonConfig(
        mode=DaemonMode.ACCELERATED,
        cycle_interval_seconds=0.05,
        max_cycles=2,
        data_dir=str(temp_daemon_env),
        initial_capital=750_000.0,
        force_market_open=True,
    )
    d1 = PaperTradingDaemon(config=cfg)
    res1 = d1.run_single_cycle()
    account1 = d1.orchestrator.broker.get_account()
    d1.stop()

    # Create second daemon pointing to identical data_dir with auto_load_state=True
    cfg2 = DaemonConfig(
        mode=DaemonMode.ACCELERATED,
        data_dir=str(temp_daemon_env),
        auto_load_state=True,
    )
    d2 = PaperTradingDaemon(config=cfg2)
    account2 = d2.orchestrator.broker.get_account()

    # Exact cash, equity, and positions must match
    assert abs(account1.cash - account2.cash) < 1e-4
    assert abs(account1.total_equity - account2.total_equity) < 1e-4
    assert d2.orchestrator.telemetry.restart_recoveries >= 1
    d2.stop()


def test_daemon_fail_closed_live_trading_barrier(temp_daemon_env):
    """Verify daemon unconditionally rejects any broker adapter reporting live capabilities."""
    class FakeLiveBroker(PaperBroker):
        @property
        def supports_live_orders(self) -> bool:
            return True

    live_broker = FakeLiveBroker(initial_capital=100_000.0)

    with pytest.raises(LiveTradingDisabledError):
        orch = PaperTradingOrchestrator(
            broker=live_broker,
            data_dir=str(temp_daemon_env),
        )
        daemon = PaperTradingDaemon(orchestrator=orch)


def test_daemon_25_cycle_endurance_soak_run(temp_daemon_env):
    """
    Execute an intensive 25-cycle endurance soak run in accelerated mode.
    Audits 4 core quantitative invariants after every cycle:
      1. Cash non-negative (Cash >= 0).
      2. No shorting (Shares >= 0).
      3. Total equity identity (Equity == Cash + sum(Shares * Price)).
      4. Reconciliation clean status (status == MATCH).
    """
    cfg = DaemonConfig(
        mode=DaemonMode.ACCELERATED,
        data_dir=str(temp_daemon_env),
        initial_capital=1_000_000.0,
        force_market_open=True,
    )
    daemon = PaperTradingDaemon(config=cfg)

    report: SoakReport = daemon.run_soak(num_cycles=25)

    assert report.cycles_completed == 25, f"Expected 25 cycles, got {report.cycles_completed}"
    assert report.all_invariants_passed is True, f"Invariant failures: {report.audit_messages}"
    assert report.cash_invariant_passed is True
    assert report.position_invariant_passed is True
    assert report.equity_identity_passed is True
    assert report.reconciliation_invariant_passed is True
    assert report.final_equity > 0.0

    daemon.stop()


def test_run_py_paper_mode_configuration():
    """Verify run.py parses paper trading arguments cleanly."""
    import run

    test_args = ["run.py", "paper", "--accelerated", "--interval", "10", "--soak", "5", "--capital", "500000"]
    old_argv = sys.argv
    try:
        sys.argv = test_args
        args = run.parse_args()
        assert args.mode == "paper"
        assert args.accelerated is True
        assert args.interval == 10.0
        assert args.soak == 5
        assert args.capital == 500_000.0
    finally:
        sys.argv = old_argv
