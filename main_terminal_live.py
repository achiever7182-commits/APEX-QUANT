"""Live terminal dashboard for the tick-driven Binance testnet bot.

Run with:
    python main_terminal_live.py    # standalone
    python run.py terminal          # via unified launcher

Market data arrives through BinanceWebSocketAdapter. Orders still use the
existing REST adapter because websocket trade streams are market-data only.
"""

from __future__ import annotations

import sys
import threading
from collections import deque
from typing import Any

from rich import box
from rich.console import Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from adapters.binance_adapter import BinanceTestnetAdapter
from adapters.binance_websocket_adapter import BinanceWebSocketAdapter
from core.risk_manager import RiskConfig, RiskManager
from core.strategy import Signal
from core.tick_strategy import TickMomentumStrategy
from core.strategies import list_strategies
from core.execution import execute_order, fee_tracker
from state.store import StateStore
from config import (
    API_KEY, API_SECRET, SYMBOL, WS_SYMBOL, LOG_LIMIT,
    THRESHOLD_PCT, WINDOW_SIZE, MIN_SECONDS_BETWEEN_TRADES,
    DRY_RUN, validate_keys,
)
from utils import order_fill_price, timestamp, log_trade

# Dashboard web emit — only active when run.py dashboard mode is used
try:
    from dashboard.server import emit_state as _emit_state
except Exception:
    _emit_state = None


_strategy_name: str = "tick"


def set_strategy(name: str) -> None:
    """Validate and set strategy for terminal live mode."""
    global _strategy_name
    name = name.lower()
    if name in ("tick", "momentum", "tick_momentum"):
        _strategy_name = "tick"
    elif name in list_strategies():
        print(
            f"[terminal] Error: '{name}' is a candle-based strategy.\n"
            f"This mode only supports tick-based strategies (e.g. 'tick').\n"
            f"Use polling mode for {name.upper()}:\n"
            f"    python run.py polling --strategy {name}"
        )
        sys.exit(1)
    else:
        print(f"[terminal] Error: Unknown strategy '{name}'. Available: {list_strategies()} or 'tick'")
        sys.exit(1)


def _push_web(state: dict, new_action: dict | None = None) -> None:
    """Push state snapshot to the web dashboard if it is running."""
    payload = {
        "symbol":           SYMBOL,
        "price":            state.get("price", 0.0),
        "signal":           state.get("signal", "HOLD"),
        "realized_pnl":     state.get("realized_pnl", 0.0),
        "unrealized_pnl":   state.get("unrealized_pnl", 0.0),
        "daily_pnl":        state.get("realized_pnl", 0.0),
        "trade_count":      state.get("trade_count", 0),
        "win_count":        state.get("wins", 0),
        "loss_count":       state.get("loss_count", 0),
        "win_rate":         round((state.get("wins", 0) / (state.get("wins", 0) + state.get("loss_count", 0)) * 100), 1) if (state.get("wins", 0) + state.get("loss_count", 0)) else 0.0,
        "total_fees_paid":  getattr(fee_tracker, "total_fees", 0.0),
        "position_open":    bool(state.get("position_amount", 0.0)),
        "position_size":    state.get("position_amount", 0.0),
        "entry_price":      state.get("entry_price", 0.0),
        "starting_balance": state.get("starting_balance", 82359.55),
        "balance":          state.get("balance", 82359.55),
        "last_action":      new_action,
        "actions":          list(state.get("actions", [])),
        "is_bot_running":   True,
    }

    def _worker():
        try:
            import json
            import urllib.request
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                "http://127.0.0.1:5000/api/telemetry",
                data=data,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=0.3):
                pass
        except Exception:
            pass
        if _emit_state is not None:
            try:
                _emit_state(payload)
            except Exception:
                pass

    threading.Thread(target=_worker, daemon=True).start()


def build_dashboard(state: dict[str, Any]) -> Panel:
    signal = state["signal"]
    signal_style = {"BUY": "bold green", "SELL": "bold red", "HOLD": "bold yellow"}[signal]
    position_text = "OPEN" if state["position_amount"] else "FLAT"
    unrealized = state["unrealized_pnl"]
    unrealized_style = "green" if unrealized >= 0 else "red"

    metrics = Table.grid(expand=True, padding=(0, 2))
    metrics.add_column(style="bright_black", justify="right")
    metrics.add_column(style="bold white", justify="left")
    metrics.add_column(style="bright_black", justify="right")
    metrics.add_column(style="bold white", justify="left")
    metrics.add_row("PRICE", f"{state['price']:,.2f} USDT", "SIGNAL", Text(signal, style=signal_style))
    metrics.add_row("TICK TIME", state["tick_timestamp"], "POSITION", position_text)
    metrics.add_row(
        "REALIZED P&L",
        f"{state['realized_pnl']:+,.4f} USDT",
        "UNREALIZED P&L",
        Text(f"{unrealized:+,.4f} USDT", style=unrealized_style),
    )
    metrics.add_row("TRADES", str(state["trade_count"]), "WINS", str(state["wins"]))

    activity = Table(show_header=True, header_style="bold cyan", box=box.SIMPLE)
    activity.add_column("Time", no_wrap=True)
    activity.add_column("Action", no_wrap=True)
    activity.add_column("Price", justify="right")
    activity.add_column("P&L", justify="right")
    activity.add_column("Order", overflow="ellipsis")
    if state["actions"]:
        for action in state["actions"]:
            pnl = action["pnl"]
            pnl_text = "-" if pnl is None else f"{pnl:+,.4f}"
            activity.add_row(action["timestamp"], action["action"], f"{action['price']:,.2f}", pnl_text, action["order_id"])
    else:
        activity.add_row("-", "Waiting", "-", "-", "No orders yet")

    return Panel(
        Group(
            Text(f"{SYMBOL}  //  TICK MOMENTUM EXECUTION", style="bold white"),
            metrics,
            Text("\nLAST 10 EXECUTED ACTIONS", style="bold magenta"),
            activity,
            Text("Ctrl+C to stop and print the session summary", style="bright_black"),
        ),
        title=" LIVE TERMINAL // BINANCE TESTNET ",
        border_style="bright_blue",
    )


def run() -> None:
    if not validate_keys():
        return

    order_adapter = BinanceTestnetAdapter(API_KEY, API_SECRET, symbol=SYMBOL)
    websocket_adapter = BinanceWebSocketAdapter(symbol=WS_SYMBOL)
    strategy = TickMomentumStrategy(threshold_pct=THRESHOLD_PCT, window_size=WINDOW_SIZE)
    starting_balance = order_adapter.fetch_balance("USDT")
    min_notional = order_adapter.get_min_notional()
    # A fast display is not permission to trade every tick: cooldown, position,
    # and daily-loss limits still protect the account from fee-burning and runaway loss.
    risk = RiskManager(
        starting_balance=starting_balance,
        config=RiskConfig(
            min_seconds_between_trades=MIN_SECONDS_BETWEEN_TRADES,
            min_notional=min_notional,
        ),
    )

    store = StateStore()
    persisted = store.load()
    if not DRY_RUN:
        persisted = store.reconcile_with_exchange(persisted, order_adapter, base_asset="BTC")

    state: dict[str, Any] = {
        "price": 0.0,
        "tick_timestamp": "Waiting for first tick...",
        "signal": "HOLD",
        "realized_pnl": float(persisted.get("realized_pnl", 0.0)),
        "unrealized_pnl": 0.0,
        "trade_count": int(persisted.get("trade_count", 0)),
        "wins": int(persisted.get("win_count", 0)),
        "loss_count": int(persisted.get("loss_count", 0)),
        "position_amount": 0.0,
        "entry_price": 0.0,
        "entry_fee": 0.0,
        "entry_time": "",
        "actions": deque(maxlen=LOG_LIMIT),
    }

    if persisted.get("trade_history"):
        for th in persisted.get("trade_history", []):
            state["actions"].appendleft({
                "timestamp": th.get("entry_time", ""),
                "action": "BUY",
                "price": float(th.get("entry_price", 0.0)),
                "pnl": None,
                "order_id": str(th.get("entry_order_id") or ""),
            })
            state["actions"].appendleft({
                "timestamp": th.get("exit_time", ""),
                "action": "SELL",
                "price": float(th.get("exit_price", 0.0)),
                "pnl": th.get("pnl", 0.0),
                "order_id": str(th.get("exit_order_id") or ""),
            })

    if persisted.get("open_position"):
        open_pos = persisted["open_position"]
        state["position_amount"] = float(open_pos.get("size", 0.0))
        state["entry_price"] = float(open_pos.get("entry_price", 0.0))
        state["entry_fee"] = float(open_pos.get("entry_fee", 0.0))
        state["entry_time"] = str(open_pos.get("entry_time", ""))
        strategy.set_open_position(
            entry_price=float(open_pos.get("entry_price", 0.0)),
            entry_time=str(open_pos.get("entry_time", "")),
        )
        risk.open_positions = 1
        state["actions"].appendleft({
            "timestamp": open_pos.get("entry_time", ""),
            "action": "BUY",
            "price": float(open_pos.get("entry_price", 0.0)),
            "pnl": None,
            "order_id": str(open_pos.get("order_id") or ""),
        })
    if persisted.get("daily_pnl"):
        risk.daily_pnl = float(persisted["daily_pnl"])

    state_lock = threading.Lock()

    def update_dashboard(price: float, tick_time: str, signal: str) -> None:
        with state_lock:
            state["price"] = price
            state["tick_timestamp"] = tick_time
            state["signal"] = signal
            if state["position_amount"]:
                gross_unrealized = (price - state["entry_price"]) * state["position_amount"]
                est_exit_fee = price * state["position_amount"] * 0.001
                state["unrealized_pnl"] = gross_unrealized - state["entry_fee"] - est_exit_fee

    def handle_tick(tick: dict[str, Any]) -> None:
        price = float(tick["price"])
        tick_time = timestamp()
        strategy_signal = strategy.on_tick(price)
        display_signal = "SELL" if strategy_signal == Signal.CLOSE else strategy_signal.value
        update_dashboard(price, tick_time, display_signal)

        new_action: dict[str, Any] | None = None

        if strategy_signal == Signal.BUY and risk.can_open_position():
            capital = risk.position_size()
            if not risk.check_min_notional(capital):
                return
            amount = capital / price
            buy_ts = timestamp(False)

            if DRY_RUN:
                sim_fee = price * amount * 0.001
                new_action = {
                    "timestamp": buy_ts,
                    "action": "BUY (DRY)",
                    "price": price,
                    "pnl": None,
                    "order_id": "dry_run",
                }
                with state_lock:
                    state["position_amount"] = amount
                    state["entry_price"] = price
                    state["entry_fee"] = sim_fee
                    state["entry_time"] = buy_ts
                    state["actions"].appendleft(new_action)
                strategy.set_open_position(price, buy_ts)
                risk.open_positions += 1
                risk.mark_trade_executed()
                log_trade(new_action["action"], buy_ts, price, amount)
            else:
                try:
                    fill = execute_order(order_adapter, "buy", amount, price)
                    new_action = {
                        "timestamp": buy_ts,
                        "action": f"BUY ({fill.method.upper()})",
                        "price": fill.fill_price,
                        "pnl": None,
                        "order_id": str(fill.order_id),
                    }
                    with state_lock:
                        state["position_amount"] = fill.filled_qty
                        state["entry_price"] = fill.fill_price
                        state["entry_fee"] = fill.fee_paid
                        state["entry_time"] = buy_ts
                        state["actions"].appendleft(new_action)
                    strategy.set_open_position(fill.fill_price, buy_ts)
                    risk.open_positions += 1
                    risk.mark_trade_executed()
                    log_trade(new_action["action"], buy_ts, fill.fill_price, fill.filled_qty)
                    persisted["open_position"] = {
                        "entry_price": fill.fill_price,
                        "size": fill.filled_qty,
                        "entry_time": buy_ts,
                        "side": "long",
                        "entry_fee": fill.fee_paid,
                        "order_id": str(fill.order_id),
                    }
                    store.save(persisted)
                except Exception as error:
                    strategy.reset_position()
                    with state_lock:
                        state["signal"] = "HOLD"
                    print(f"[{timestamp(False)}] BUY failed: {error}")

        elif strategy_signal == Signal.CLOSE and risk.open_positions > 0 and risk.can_close_position():
            with state_lock:
                amount = state["position_amount"]
                entry_price = state["entry_price"]
                entry_fee = state["entry_fee"]
                entry_time = state.get("entry_time") or ""

            open_pos = persisted.get("open_position") or {}
            if not entry_time:
                entry_time = open_pos.get("entry_time", "")
            open_order_id = open_pos.get("order_id", "")
            sell_ts = timestamp(False)

            if DRY_RUN:
                est_exit_fee = price * amount * 0.001
                gross_pnl = (price - entry_price) * amount
                net_pnl = gross_pnl - entry_fee - est_exit_fee
                risk.record_trade_result(net_pnl)
                new_action = {
                    "timestamp": sell_ts,
                    "action": "SELL (DRY)",
                    "price": price,
                    "pnl": net_pnl,
                    "order_id": "dry_run",
                }
                with state_lock:
                    state["realized_pnl"] += net_pnl
                    state["unrealized_pnl"] = 0.0
                    state["position_amount"] = 0.0
                    state["entry_price"] = 0.0
                    state["entry_fee"] = 0.0
                    state["entry_time"] = ""
                    state["trade_count"] += 1
                    if net_pnl > 0:
                        state["wins"] += 1
                    elif net_pnl < 0:
                        state["loss_count"] += 1
                    state["actions"].appendleft(new_action)
                strategy.reset_position()
                risk.open_positions -= 1
                risk.mark_trade_executed()
                log_trade(new_action["action"], sell_ts, price, amount)
            else:
                try:
                    fill = execute_order(order_adapter, "sell", amount, price)
                    gross_pnl = (fill.fill_price - entry_price) * amount
                    net_pnl = gross_pnl - entry_fee - fill.fee_paid
                    risk.record_trade_result(net_pnl)
                    new_action = {
                        "timestamp": sell_ts,
                        "action": f"SELL ({fill.method.upper()})",
                        "price": fill.fill_price,
                        "pnl": net_pnl,
                        "order_id": str(fill.order_id),
                    }
                    with state_lock:
                        state["realized_pnl"] += net_pnl
                        state["unrealized_pnl"] = 0.0
                        state["position_amount"] = 0.0
                        state["entry_price"] = 0.0
                        state["entry_fee"] = 0.0
                        state["entry_time"] = ""
                        state["trade_count"] += 1
                        if net_pnl > 0:
                            state["wins"] += 1
                        elif net_pnl < 0:
                            state["loss_count"] += 1
                        state["actions"].appendleft(new_action)
                    strategy.reset_position()
                    risk.open_positions -= 1
                    risk.mark_trade_executed()
                    log_trade(new_action["action"], sell_ts, fill.fill_price, fill.filled_qty)
                    store.record_trade(
                        persisted,
                        entry_price=entry_price,
                        exit_price=fill.fill_price,
                        size=amount,
                        pnl=net_pnl,
                        fee=entry_fee + fill.fee_paid,
                        entry_time=entry_time or sell_ts,
                        exit_time=sell_ts,
                        entry_order_id=open_order_id,
                        exit_order_id=str(fill.order_id),
                    )
                except Exception as error:
                    print(f"[{timestamp(False)}] SELL failed: {error}")

        with state_lock:
            snap = dict(state)
            snap["starting_balance"] = starting_balance
            snap["balance"] = starting_balance + state["realized_pnl"]
        _push_web(snap, new_action=new_action)
        live.update(build_dashboard(state))

    live = Live(build_dashboard(state), refresh_per_second=30, screen=True)
    try:
        with live:
            live.update(build_dashboard(state))
            websocket_adapter.start(on_tick=handle_tick)
            threading.Event().wait()
    except KeyboardInterrupt:
        websocket_adapter.stop()
    finally:
        with state_lock:
            trade_count = state["trade_count"]
            realized_pnl = state["realized_pnl"]
            wins = state["wins"]
        win_rate = (wins / trade_count * 100) if trade_count else 0.0
        print("\nSession summary")
        print(f"Total trades: {trade_count}")
        print(f"Total realized P&L: {realized_pnl:+.4f} USDT")
        print(f"Win rate: {win_rate:.1f}%")


if __name__ == "__main__":
    run()