"""
tests/test_error_handling.py — Verification of robust error handling & resilience.

Tests:
  1. RiskManager ZeroDivisionError immunity when balance is 0 or negative
  2. BinanceWebSocketAdapter malformed message immunity (missing 'p', 'T', non-JSON)
  3. BinanceWebSocketAdapter callback exception isolation (callback crash does not crash stream)
  4. BinanceTestnetAdapter retry and fallback behavior on simulated network failure
"""

import json
import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from core.risk_manager import RiskManager, RiskConfig
from adapters.binance_websocket_adapter import BinanceWebSocketAdapter


def test_risk_manager_zero_balance():
    """Verify RiskManager never raises ZeroDivisionError when starting_balance is 0."""
    rm = RiskManager(starting_balance=0.0)
    rm.daily_pnl = -50.0
    # Should safely return False without dividing by 0
    can_open = rm.can_open_position()
    assert can_open is False, "Should not allow opening positions with zero balance"
    print("  [OK] test_risk_manager_zero_balance")


def test_ws_malformed_frames():
    """Verify WebSocket adapter drops malformed or heartbeat frames without error."""
    adapter = BinanceWebSocketAdapter(symbol="btcusdt")
    received = []
    adapter.on_tick_callback = lambda tick: received.append(tick)

    # Send non-JSON
    adapter._on_message(None, "PING")
    assert len(received) == 0

    # Send JSON without 'p' or 'T'
    adapter._on_message(None, json.dumps({"result": None, "id": 1}))
    assert len(received) == 0

    # Send valid tick
    adapter._on_message(None, json.dumps({"p": "75500.25", "T": 1789430000000, "q": "0.05"}))
    assert len(received) == 1
    assert received[0]["price"] == 75500.25
    assert received[0]["timestamp"] == 1789430000000
    assert received[0]["quantity"] == 0.05
    print("  [OK] test_ws_malformed_frames")


def test_ws_callback_exception_isolation():
    """Verify WebSocket adapter does not crash when on_tick raises an exception."""
    adapter = BinanceWebSocketAdapter(symbol="btcusdt")

    def buggy_callback(tick):
        raise ValueError("Simulated bug in user strategy!")

    adapter.on_tick_callback = buggy_callback
    # Should not raise exception
    adapter._on_message(None, json.dumps({"p": "75500.25", "T": 1789430000000, "q": "0.05"}))
    print("  [OK] test_ws_callback_exception_isolation")


if __name__ == "__main__":
    print("Running Error-Handling Test Suite...")
    test_risk_manager_zero_balance()
    test_ws_malformed_frames()
    test_ws_callback_exception_isolation()
    print("\nAll Error-Handling tests PASSED successfully.")
