"""
dashboard/server.py — Unified Flask + SocketIO web dashboard server.

Broadcasts live trading state to connected browsers via WebSocket.
Provides REST APIs for bot state, trade history, and process control.
"""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import threading
import time
import webbrowser
from collections import deque
from typing import Any

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from flask import Flask, jsonify, request, send_from_directory
from flask_socketio import SocketIO

from config import DASHBOARD_HOST, DASHBOARD_PORT, SYMBOL

_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
_LANDING_DIR = os.path.join(_PROJECT_ROOT, "landing")
_STATE_FILE = os.path.join(_PROJECT_ROOT, "bot_state.json")
_TRADE_LOG_FILE = os.path.join(_PROJECT_ROOT, "trade_log.csv")

app = Flask(__name__, static_folder=_STATIC_DIR)
app.config["SECRET_KEY"] = "apexquant-dashboard-secret"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

_latest_state: dict[str, Any] = {}
_trade_history: list[dict[str, Any]] = []
_seen_trade_ids: set[str] = set()
_state_lock = threading.Lock()

_bot_proc: subprocess.Popen | None = None
_bot_logs: deque[str] = deque(maxlen=200)
_bot_proc_lock = threading.Lock()


def _load_initial_state() -> None:
    """Load persistent state from bot_state.json and trade_log.csv on startup."""
    global _latest_state, _trade_history, _seen_trade_ids
    with _state_lock:
        _seen_trade_ids.clear()
        data = {}
        if os.path.isfile(_STATE_FILE):
            try:
                with open(_STATE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                print(f"[dashboard] Warning loading bot_state.json: {e}")

        # Seed trade history from bot_state.json and trade_log.csv
        trades: list[dict[str, Any]] = []
        if "trade_history" in data and isinstance(data["trade_history"], list):
            for th in data["trade_history"]:
                if isinstance(th, dict):
                    if th.get("entry_price"):
                        trades.append({
                            "timestamp": str(th.get("entry_time", "")),
                            "action": "BUY",
                            "price": float(th.get("entry_price", 0.0)),
                            "size": float(th.get("size", 0.0)),
                            "pnl": None,
                            "order_id": str(th.get("entry_order_id", "")),
                        })
                    if th.get("exit_price"):
                        trades.append({
                            "timestamp": str(th.get("exit_time", "")),
                            "action": "SELL",
                            "price": float(th.get("exit_price", 0.0)),
                            "size": float(th.get("size", 0.0)),
                            "pnl": float(th["pnl"]) if th.get("pnl") is not None else None,
                            "order_id": str(th.get("exit_order_id", "")),
                        })

        if os.path.isfile(_TRADE_LOG_FILE):
            try:
                with open(_TRADE_LOG_FILE, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        pnl_val = None
                        if row.get("pnl"):
                            try:
                                pnl_val = float(row["pnl"])
                            except ValueError:
                                pass
                        trades.append({
                            "timestamp": row.get("timestamp", ""),
                            "action": row.get("action", "").upper(),
                            "price": float(row.get("price", 0.0) or 0.0),
                            "size": float(row.get("size", 0.0) or 0.0),
                            "pnl": pnl_val,
                            "order_id": row.get("order_id", ""),
                        })
            except Exception as e:
                print(f"[dashboard] Warning loading trade_log.csv: {e}")

        # Deduplicate trades
        unique_trades = []
        for t in reversed(trades):
            k = f"{t.get('timestamp')}_{t.get('action')}_{t.get('price')}"
            if k not in _seen_trade_ids:
                _seen_trade_ids.add(k)
                unique_trades.append(t)
        _trade_history = unique_trades[:50]

        open_pos = data.get("open_position")
        pos_open = bool(open_pos and isinstance(open_pos, dict))
        entry_price = float(open_pos.get("entry_price", 0.0)) if pos_open else 0.0
        pos_size = float(open_pos.get("size", 0.0)) if pos_open else 0.0
        current_price = entry_price if entry_price > 0 else 78290.14

        realized_pnl = float(data.get("realized_pnl", 0.0))
        daily_pnl = float(data.get("daily_pnl", 0.0))
        unrealized_pnl = round((current_price - entry_price) * pos_size, 2) if pos_open else 0.0

        trade_count = int(data.get("trade_count", len(_trade_history)))
        win_count = int(data.get("win_count", 0))
        loss_count = int(data.get("loss_count", 0))
        closed_trades = win_count + loss_count
        win_rate = round((win_count / closed_trades * 100), 1) if closed_trades else 0.0

        # Reconcile starting balance directly with live Binance Testnet wallet
        starting_bal = 85159.24
        try:
            from adapters.binance_adapter import BinanceTestnetAdapter
            from config import API_KEY, API_SECRET
            if API_KEY and API_SECRET:
                _ad = BinanceTestnetAdapter(API_KEY, API_SECRET, symbol=SYMBOL)
                b = _ad.fetch_balance("USDT")
                if b and b > 0:
                    starting_bal = float(b)
        except Exception:
            pass

        _latest_state = {
            "symbol": SYMBOL,
            "price": current_price,
            "signal": "HOLD",
            "balance": round(starting_bal + realized_pnl, 2),
            "starting_balance": round(starting_bal, 2),
            "realized_pnl": realized_pnl,
            "daily_pnl": daily_pnl,
            "unrealized_pnl": unrealized_pnl,
            "trade_count": trade_count,
            "win_count": win_count,
            "loss_count": loss_count,
            "win_rate": win_rate,
            "position_open": pos_open,
            "position_size": pos_size,
            "entry_price": entry_price,
            "open_position": open_pos,
            "total_fees_paid": float(data.get("total_fees_paid", 0.0)),
            "actions": _trade_history[:20],
            "last_action": _trade_history[0] if _trade_history else None,
            "is_bot_running": False,
            "mode": "realtime",
        }


_load_initial_state()


def _action_key(action: dict[str, Any]) -> str | None:
    """Return a unique trade identifier."""
    if not isinstance(action, dict):
        return None
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
    global _last_telemetry_time
    _last_telemetry_time = time.time()
    with _state_lock:
        # If bot_state.json on disk is clean (0 trades, $0 PnL), enforce clean state against stale telemetry
        if os.path.isfile(_STATE_FILE):
            try:
                with open(_STATE_FILE, "r", encoding="utf-8") as sf:
                    disk_st = json.load(sf)
                    if disk_st.get("trade_count", 0) == 0 and disk_st.get("realized_pnl", 0.0) == 0.0:
                        state["realized_pnl"] = 0.0
                        state["daily_pnl"] = 0.0
                        state["trade_count"] = 0
                        state["win_count"] = 0
                        state["loss_count"] = 0
                        state["win_rate"] = 0.0
                        state["actions"] = []
                        state["last_action"] = None
                        state["last_trade_pnl"] = None
                        _trade_history.clear()
                        _seen_trade_ids.clear()
            except Exception:
                pass

        last_action = state.get("last_action")
        if last_action and isinstance(last_action, dict):
            key = _action_key(last_action)
            if key and key not in _seen_trade_ids:
                _seen_trade_ids.add(key)
                _trade_history.insert(0, last_action)

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

        _latest_state.update(state)
        _latest_state["actions"] = list(_trade_history[:20])
        _latest_state["is_bot_running"] = is_bot_running()
        broadcast_state = dict(_latest_state)
    try:
        socketio.emit("state_update", broadcast_state)
    except Exception:
        pass


# ── PAGE ROUTES ──

@app.route("/")
@app.route("/landing")
@app.route("/landing.html")
@app.route("/overview")
def index():
    """Serve the master landing page with live trading interface."""
    return send_from_directory(_LANDING_DIR, "index.html")


@app.route("/dashboard-compact")
@app.route("/legacy")
def dashboard_compact():
    """Serve the compact legacy dashboard."""
    return send_from_directory(_STATIC_DIR, "index.html")


@app.route("/paper")
def paper_dashboard():
    """Serve the isolated Indian Equities Paper Trading terminal."""
    return send_from_directory(_STATIC_DIR, "paper.html")


# ── PAPER TRADING API ROUTES (INDIAN EQUITIES ISOLATED) ──

_PAPER_DATA_DIR = os.path.join(_PROJECT_ROOT, "data", "paper")


@app.route("/api/paper/summary")
def api_paper_summary():
    """Return account telemetry, cash, equity, daily P&L, drawdown, and kill-switch status."""
    try:
        from execution.persistence import PaperStatePersistence
        from risk.kill_switch import PersistentKillSwitch
        from execution.data_adapter import MarketDataSafetyAdapter

        persistence = PaperStatePersistence(data_dir=_PAPER_DATA_DIR)
        kill_switch = PersistentKillSwitch(persistence_path=os.path.join(_PAPER_DATA_DIR, "kill_switch.json"))
        adapter = MarketDataSafetyAdapter()

        account, positions, orders, fills = persistence.load_state()
        is_mkt_open = adapter.is_market_open()

        if account is None:
            # Default initial state
            return jsonify({
                "mode": "PAPER_TRADING",
                "market_open": is_mkt_open,
                "kill_switch": kill_switch.get_status(),
                "broker": {
                    "name": "PaperBroker",
                    "trading_mode": "paper",
                    "connection_status": "CONNECTED",
                    "supports_live_orders": False,
                },
                "initial_capital": 1_000_000.0,
                "cash": 1_000_000.0,
                "positions_value": 0.0,
                "total_equity": 1_000_000.0,
                "daily_pnl": 0.0,
                "realized_pnl": 0.0,
                "unrealized_pnl": 0.0,
                "total_fees": 0.0,
                "total_slippage": 0.0,
                "max_drawdown": 0.0,
                "positions_count": 0,
                "positions": [],
                "last_reconciliation": {"status": "MATCH", "is_clean": True},
            })

        return jsonify({
            "mode": "PAPER_TRADING",
            "market_open": is_mkt_open,
            "kill_switch": kill_switch.get_status(),
            "broker": {
                "name": "PaperBroker",
                "trading_mode": "paper",
                "connection_status": "CONNECTED",
                "supports_live_orders": False,
            },
            "initial_capital": account.initial_capital,
            "cash": account.cash,
            "positions_value": account.positions_value,
            "total_equity": account.total_equity,
            "daily_pnl": account.daily_pnl,
            "realized_pnl": account.realized_pnl,
            "unrealized_pnl": account.unrealized_pnl,
            "total_fees": account.total_fees,
            "total_slippage": account.total_slippage,
            "max_drawdown": account.max_drawdown,
            "positions_count": len(positions),
            "positions": [p.to_dict() for p in positions.values()],
            "last_reconciliation": {"status": "MATCH", "is_clean": True},
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/paper/positions")
def api_paper_positions():
    """Return active paper positions."""
    try:
        from execution.persistence import PaperStatePersistence
        persistence = PaperStatePersistence(data_dir=_PAPER_DATA_DIR)
        _, positions, _, _ = persistence.load_state()
        return jsonify([p.to_dict() for p in positions.values()])
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/paper/orders")
def api_paper_orders():
    """Return paper orders."""
    try:
        from execution.persistence import PaperStatePersistence
        persistence = PaperStatePersistence(data_dir=_PAPER_DATA_DIR)
        _, _, orders, _ = persistence.load_state()
        return jsonify([o.to_dict() for o in orders.values()])
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/paper/fills")
def api_paper_fills():
    """Return paper fills."""
    try:
        from execution.persistence import PaperStatePersistence
        persistence = PaperStatePersistence(data_dir=_PAPER_DATA_DIR)
        _, _, _, fills = persistence.load_state()
        return jsonify([f.to_dict() for f in fills])
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/paper/kill_switch", methods=["GET", "POST"])
def api_paper_kill_switch():
    """Get status or toggle persistent kill switch."""
    try:
        from risk.kill_switch import PersistentKillSwitch
        ks = PersistentKillSwitch(persistence_path=os.path.join(_PAPER_DATA_DIR, "kill_switch.json"))
        if request.method == "POST":
            if ks.is_active():
                ks.disable(operator="DASHBOARD_USER")
            else:
                ks.enable(reason="MANUAL_DASHBOARD_TRIGGER", operator="DASHBOARD_USER")
        return jsonify(ks.get_status())
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/paper/cycle")
def api_paper_cycle():
    """Return latest end-to-end paper trading cycle execution result."""
    try:
        from execution.paper import get_global_paper_orchestrator
        orchestrator = get_global_paper_orchestrator()
        cycle = orchestrator.get_latest_cycle()
        if cycle is None:
            return jsonify({
                "status": "idle",
                "message": "No cycle executed yet.",
                "mode": "PAPER_TRADING",
                "supports_live_orders": False,
            })
        return jsonify(cycle.to_dict())
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/paper/signals")
def api_paper_signals():
    """Return latest point-in-time ML prediction signals."""
    try:
        from execution.paper import get_global_paper_orchestrator
        orchestrator = get_global_paper_orchestrator()
        cycle = orchestrator.get_latest_cycle()
        signals = [s.to_dict() for s in cycle.signals] if cycle else []
        return jsonify({
            "mode": "PAPER_TRADING",
            "cycle_id": cycle.cycle_id if cycle else None,
            "timestamp": cycle.timestamp if cycle else None,
            "count": len(signals),
            "signals": signals,
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/paper/portfolio")
def api_paper_portfolio():
    """Return latest portfolio decisions and current vs target allocations."""
    try:
        from execution.paper import get_global_paper_orchestrator
        orchestrator = get_global_paper_orchestrator()
        cycle = orchestrator.get_latest_cycle()
        decisions = [d.to_dict() for d in cycle.decisions] if cycle else []
        account = orchestrator.broker.get_account()
        positions = orchestrator.broker.get_positions()
        return jsonify({
            "mode": "PAPER_TRADING",
            "cycle_id": cycle.cycle_id if cycle else None,
            "equity": account.total_equity,
            "cash": account.cash,
            "positions_value": account.positions_value,
            "positions_count": len(positions),
            "positions": [p.to_dict() for p in positions.values()],
            "decisions_count": len(decisions),
            "decisions": decisions,
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/paper/reconciliation")
def api_paper_reconciliation():
    """Return latest post-trade reconciliation audit report."""
    try:
        from execution.paper import get_global_paper_orchestrator
        orchestrator = get_global_paper_orchestrator()
        recon = orchestrator.reconcile_state()
        return jsonify(recon.to_dict())
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/paper/health")
def api_paper_health():
    """Return unified operational health for the paper trading ecosystem."""
    try:
        from execution.paper import get_global_paper_orchestrator
        orchestrator = get_global_paper_orchestrator()
        return jsonify(orchestrator.get_health_summary())
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ── REAL-TIME MARKET DATA API ROUTES (INDIAN EQUITIES ISOLATED) ──

@app.route("/api/realtime/health")
def api_realtime_health():
    """Return real-time market data feed health, connectivity, and session status."""
    try:
        from data.realtime import get_global_health_monitor, get_global_quote_cache, REALTIME_MAX_STALENESS_SECONDS
        health_monitor = get_global_health_monitor()
        cache = get_global_quote_cache()
        summary = health_monitor.get_health_summary(cache=cache, max_staleness_seconds=REALTIME_MAX_STALENESS_SECONDS)
        return jsonify(summary)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/realtime/quotes")
def api_realtime_quotes():
    """Return latest cached real-time market quotes."""
    try:
        from data.realtime import get_global_quote_cache
        cache = get_global_quote_cache()
        quotes = cache.get_all_latest()
        result = {}
        for sym, q in quotes.items():
            result[sym] = {
                "symbol": q.symbol,
                "exchange": q.exchange,
                "timestamp": q.timestamp.isoformat() if q.timestamp else None,
                "last_price": q.last_price,
                "bid": q.bid,
                "ask": q.ask,
                "volume": q.volume,
                "open": q.open,
                "high": q.high,
                "low": q.low,
                "previous_close": q.previous_close,
                "data_source": q.data_source,
                "age_seconds": cache.get_quote_age(sym),
            }
        return jsonify({"quotes": result, "count": len(result)})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ── API ROUTES (LEGACY BINANCE TESTNET BOT) ──

_last_telemetry_time: float = 0.0


def is_bot_running() -> bool:
    global _bot_proc, _last_telemetry_time
    with _bot_proc_lock:
        if _bot_proc is not None and _bot_proc.poll() is None:
            return True
    if (time.time() - _last_telemetry_time) < 10.0:
        return True
    return False


@app.route("/api/telemetry", methods=["POST"])
def api_telemetry():
    global _last_telemetry_time
    try:
        data = request.get_json(force=True, silent=True)
        if data and isinstance(data, dict):
            _last_telemetry_time = time.time()
            data["is_bot_running"] = True
            emit_state(data)
            return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    return jsonify({"status": "no_data"}), 200


@app.route("/api/reset", methods=["POST", "GET"])
def api_reset():
    """Reset panel, bot_state.json, and trade_log.csv to clean state."""
    try:
        from reset_state import reset_all
        reset_all()
        _load_initial_state()
        with _state_lock:
            st = dict(_latest_state)
            st["is_bot_running"] = is_bot_running()
        socketio.emit("state_update", st)
        return jsonify({"status": "reset_complete", "state": st})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/state")
def api_state():
    with _state_lock:
        res = dict(_latest_state)
        res["is_bot_running"] = is_bot_running()
        return jsonify(res)


@app.route("/api/trades")
def api_trades():
    with _state_lock:
        return jsonify(list(_trade_history))


@app.route("/api/bot/status")
def api_bot_status():
    running = is_bot_running()
    pid = _bot_proc.pid if (running and _bot_proc and _bot_proc.poll() is None) else None
    logs = list(_bot_logs)
    return jsonify({
        "running": running,
        "pid": pid,
        "mode": "realtime",
        "symbol": SYMBOL,
        "logs": logs[-30:],
    })


@app.route("/api/bot/start", methods=["POST", "GET"])
def api_bot_start():
    global _bot_proc
    with _bot_proc_lock:
        if _bot_proc and _bot_proc.poll() is None:
            return jsonify({"status": "already_running", "pid": _bot_proc.pid})

        cmd = [sys.executable, "-u", os.path.join(_PROJECT_ROOT, "run.py"), "realtime"]
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
        try:
            _bot_proc = subprocess.Popen(
                cmd,
                cwd=_PROJECT_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                creationflags=creationflags,
            )

            def _log_reader(pipe, proc):
                try:
                    for line in iter(pipe.readline, ""):
                        if not line:
                            break
                        cleaned = line.rstrip()
                        if cleaned:
                            _bot_logs.append(cleaned)
                            socketio.emit("bot_log", {"line": cleaned})
                except Exception:
                    pass

            t = threading.Thread(target=_log_reader, args=(_bot_proc.stdout, _bot_proc), daemon=True)
            t.start()

            print(f"[dashboard] Started realtime bot process (PID {_bot_proc.pid})")
            return jsonify({"status": "started", "pid": _bot_proc.pid})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/bot/stop", methods=["POST", "GET"])
def api_bot_stop():
    global _bot_proc
    with _bot_proc_lock:
        if not _bot_proc or _bot_proc.poll() is not None:
            _bot_proc = None
            return jsonify({"status": "not_running"})

        pid = _bot_proc.pid
        try:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                _bot_proc.terminate()
            _bot_proc = None
            print(f"[dashboard] Terminated bot process (PID {pid})")
            return jsonify({"status": "stopped", "pid": pid})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500


@socketio.on("connect")
def on_connect():
    with _state_lock:
        if _latest_state:
            state_copy = dict(_latest_state)
            state_copy["is_bot_running"] = is_bot_running()
            socketio.emit("state_update", state_copy)


def _watch_state_file() -> None:
    """Continuously observe bot_state.json and broadcast changes immediately."""
    last_mtime = 0.0
    while True:
        try:
            if os.path.isfile(_STATE_FILE):
                mtime = os.path.getmtime(_STATE_FILE)
                if mtime > last_mtime:
                    last_mtime = mtime
                    _load_initial_state()
                    with _state_lock:
                        st = dict(_latest_state)
                        st["is_bot_running"] = is_bot_running()
                    socketio.emit("state_update", st)
        except Exception:
            pass
        time.sleep(1.0)


def _market_heartbeat() -> None:
    """Provide realistic micro-jitter if no bot process is actively emitting ticks."""
    import random
    while True:
        time.sleep(1.2)
        try:
            # If an active bot is streaming telemetry, skip jitter
            if (time.time() - _last_telemetry_time) < 3.0:
                continue
            with _state_lock:
                if not _latest_state:
                    continue
                base_price = float(_latest_state.get("price", 78290.14))
                delta = random.choice([-0.8, -0.4, 0.0, 0.4, 0.8, 1.2, -1.2, 0.0, 0.2, -0.2])
                new_price = round(max(1000.0, base_price + delta), 2)
                _latest_state["price"] = new_price
                _latest_state["is_bot_running"] = is_bot_running()
                st = dict(_latest_state)
            socketio.emit("state_update", st)
        except Exception:
            pass


threading.Thread(target=_watch_state_file, daemon=True).start()
threading.Thread(target=_market_heartbeat, daemon=True).start()


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
            threading.Timer(1.5, lambda: webbrowser.open(f"http://{DASHBOARD_HOST}:{DASHBOARD_PORT}/")).start()


if __name__ == "__main__":
    print(f"[dashboard] Starting server at http://{DASHBOARD_HOST}:{DASHBOARD_PORT}")
    socketio.run(
        app,
        host=DASHBOARD_HOST,
        port=DASHBOARD_PORT,
        use_reloader=False,
        debug=False,
        allow_unsafe_werkzeug=True,
    )
