"""
dashboard/server.py — Flask + SocketIO web dashboard server.

Broadcasts live trading state to connected browsers via WebSocket.
The bot calls dashboard.emit_state(state_dict) after every tick/trade.
"""

from __future__ import annotations

import threading
import webbrowser
from collections import deque
from typing import Any

from flask import Flask, jsonify, send_from_directory
from flask_socketio import SocketIO

from config import DASHBOARD_HOST, DASHBOARD_PORT

import os

_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

app = Flask(__name__, static_folder=_STATIC_DIR)
app.config["SECRET_KEY"] = "tradingbot-dashboard-secret"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

_latest_state: dict[str, Any] = {}
_trade_history: list[dict[str, Any]] = []
_seen_trade_ids: set[str] = set()
_state_lock = threading.Lock()


def _action_key(action: dict[str, Any]) -> str | None:
    """Return a unique trade identifier: order ID if available, else timestamp+side+price combo."""
    if not isinstance(action, dict):
        return None

    # Ignore tick updates or non-trade actions
    act = str(action.get("action") or "").strip().upper()
    if not act or act in ("HOLD", "WAITING", "-", "NONE"):
        return None

    order_id = str(action.get("order_id") or "").strip()
    if order_id and order_id not in ("dry_run", "None", ""):
        return f"order_{order_id}"

    ts = str(action.get("timestamp") or "").strip()
    price = str(action.get("price") or "").strip()
    if not ts and not price:
        return None
    return f"{ts}_{act}_{price}"


def emit_state(state: dict[str, Any]) -> None:
    """Call this from the trading loop after every tick or trade."""
    with _state_lock:
        # Only append a row if a genuine new trade action just happened
        last_action = state.get("last_action")
        if last_action and isinstance(last_action, dict):
            key = _action_key(last_action)
            if key and key not in _seen_trade_ids:
                _seen_trade_ids.add(key)
                _trade_history.insert(0, last_action)

        # Ingest/seed any actions from startup snapshot without duplicating
        actions = state.get("actions")
        if actions and isinstance(actions, (list, tuple, deque)):
            for a in reversed(list(actions)):
                if isinstance(a, dict):
                    key = _action_key(a)
                    if key and key not in _seen_trade_ids:
                        _seen_trade_ids.add(key)
                        _trade_history.insert(0, a)

        if len(_trade_history) > 50:
            del _trade_history[50:]

        state["actions"] = list(_trade_history[:20])

        _latest_state.clear()
        _latest_state.update(state)
    socketio.emit("state_update", state)


@app.route("/")
def index():
    return send_from_directory(_STATIC_DIR, "index.html")


@app.route("/api/state")
def api_state():
    with _state_lock:
        return jsonify(dict(_latest_state))


@socketio.on("connect")
def on_connect():
    with _state_lock:
        if _latest_state:
            socketio.emit("state_update", dict(_latest_state))


class DashboardServer:
    """Runs the Flask/SocketIO server in a daemon thread."""

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None

    def start(self, open_browser: bool = True) -> None:
        self._thread = threading.Thread(
            target=lambda: socketio.run(
                app,
                host=DASHBOARD_HOST,
                port=DASHBOARD_PORT,
                use_reloader=False,
                log_output=False,
                allow_unsafe_werkzeug=True,
            ),
            name="dashboard-server",
            daemon=True,
        )
        self._thread.start()
        print(f"[dashboard] Live at http://{DASHBOARD_HOST}:{DASHBOARD_PORT}")
        if open_browser:
            threading.Timer(1.5, lambda: webbrowser.open(f"http://{DASHBOARD_HOST}:{DASHBOARD_PORT}")).start()
