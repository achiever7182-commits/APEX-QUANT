"""Tick-driven Binance testnet trader with a scrolling terminal dashboard.

Run with:
    python main_realtime.py      # standalone
    python run.py realtime       # via unified launcher

The websocket supplies every trade tick. A separate printer thread emits one
snapshot per second so the terminal keeps readable scrollback even when the
market is quiet or no trade is triggered.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any

import config

from rich.console import Console
from rich.style import Style

from adapters.binance_adapter import BinanceTestnetAdapter
from adapters.binance_websocket_adapter import BinanceWebSocketAdapter
from core.risk_manager import RiskConfig, RiskManager
from core.strategy import Signal, MarketData
from core.tick_strategy import TickMomentumStrategy
from core.strategies import get_strategy, list_strategies
from core.execution import execute_order, fee_tracker
from state.store import StateStore
from config import (
    API_KEY, API_SECRET, SYMBOL, WS_SYMBOL,
    PRINT_INTERVAL_SECONDS, RECONNECT_CHECK_SECONDS,
    THRESHOLD_PCT, WINDOW_SIZE, TAKE_PROFIT_PCT, STOP_LOSS_PCT, TRAILING_STOP_PCT,
    MIN_SECONDS_BETWEEN_TRADES, DRY_RUN, validate_keys,
)
from utils import order_fill_price

# Dashboard web emit — active when dashboard server is running
try:
    from dashboard.server import emit_state as _emit_state
except Exception:
    _emit_state = None


def _send_telemetry(payload: dict) -> None:
    """Send state payload to local web dashboard server if running."""
    def _worker():
        if _emit_state is not None:
            try:
                _emit_state(payload)
            except Exception:
                pass
        try:
            import json
            import urllib.request
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                "http://127.0.0.1:5000/api/telemetry",
                data=data,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=1.5):
                pass
        except Exception:
            pass

    threading.Thread(target=_worker, daemon=True).start()


_strategy_name: str = "ml" if os.path.exists(getattr(config, "ML_MODEL_PATH", "models/ml_model.joblib")) else "tick"


def set_strategy(name: str) -> None:
    """Validate and set strategy for realtime mode."""
    global _strategy_name
    name = name.lower()
    if name in ("tick", "momentum", "tick_momentum"):
        _strategy_name = "tick"
    elif name in list_strategies():
        _strategy_name = name
    else:
        print(f"[realtime] Error: Unknown strategy '{name}'. Available: {list_strategies()} or 'tick'")
        sys.exit(1)


@dataclass
class Position:
    entry_price: float
    entry_time: str
    size: float
    entry_fee: float = 0.0
    side: str = "long"


@dataclass
class ClosedTrade:
    entry_price: float
    exit_price: float
    size: float
    pnl: float
    entry_time: str
    exit_time: str


class TradingSession:
    """Owns mutable trading state shared by the websocket and printer threads."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.current_price = 0.0
        self.current_signal = Signal.HOLD.value
        self.position: Position | None = None
        self.realized_pnl = 0.0
        self.unrealized_pnl = 0.0
        self.trade_history: list[ClosedTrade] = []
        self.trade_count = 0
        self.win_count = 0
        self.loss_count = 0
        self.last_trade_pnl: float | None = None
        self.starting_balance = 82359.55
        self.started_at = time.monotonic()

    @staticmethod
    def now(milliseconds: bool = True) -> str:
        from datetime import datetime
        value = datetime.now().strftime("%H:%M:%S.%f")
        return value[:-3] if milliseconds else value

    def update_tick(self, price: float, signal: str) -> None:
        with self.lock:
            self.current_price = price
            self.current_signal = signal
            if self.position is not None:
                gross_unrealized = (price - self.position.entry_price) * self.position.size
                est_exit_fee = price * self.position.size * 0.001
                self.unrealized_pnl = gross_unrealized - self.position.entry_fee - est_exit_fee

    def open_position(self, entry_price: float, size: float, entry_time: str, entry_fee: float = 0.0) -> None:
        with self.lock:
            self.position = Position(entry_price, entry_time, size, entry_fee=entry_fee)
            self.unrealized_pnl = 0.0
            self.trade_count += 1

    def close_position(self, exit_price: float, exit_time: str, exit_fee: float = 0.0) -> float:
        with self.lock:
            if self.position is None:
                raise RuntimeError("Cannot close a position that is not open")

            position = self.position
            gross_pnl = (exit_price - position.entry_price) * position.size
            trade_pnl = gross_pnl - position.entry_fee - exit_fee
            self.trade_history.append(
                ClosedTrade(
                    entry_price=position.entry_price,
                    exit_price=exit_price,
                    size=position.size,
                    pnl=trade_pnl,
                    entry_time=position.entry_time,
                    exit_time=exit_time,
                )
            )
            self.realized_pnl += trade_pnl
            self.last_trade_pnl = trade_pnl
            self.win_count += trade_pnl > 0
            self.loss_count += trade_pnl < 0
            self.position = None
            self.unrealized_pnl = 0.0
            self.trade_count += 1
            return trade_pnl

    def snapshot(self) -> dict[str, Any]:
        # The lock is required because the websocket can update price/P&L while
        # this thread reads them. Without it, output could combine fields from
        # different ticks or observe a position halfway through a close.
        with self.lock:
            position = self.position
            closed_trades = self.win_count + self.loss_count
            return {
                "price": self.current_price,
                "signal": self.current_signal,
                "position": position,
                "realized_pnl": self.realized_pnl,
                "unrealized_pnl": self.unrealized_pnl,
                "trade_count": self.trade_count,
                "win_rate": (self.win_count / closed_trades * 100) if closed_trades else 0.0,
                "last_trade_pnl": self.last_trade_pnl,
            }


def format_position(position: Position | None) -> str:
    if position is None:
        return "NONE".ljust(13)
    return f"{position.side.upper()}@{position.entry_price:.2f}".ljust(13)


def print_snapshot(session: TradingSession, console: Console) -> None:
    snapshot = session.snapshot()
    price = snapshot["price"]
    sig = snapshot["signal"]
    pos = snapshot["position"]
    r_pnl = snapshot["realized_pnl"]
    u_pnl = snapshot["unrealized_pnl"]
    trades = snapshot["trade_count"]
    win_rate = snapshot["win_rate"]

    # High-clarity institutional terminal layout
    pnl_val = r_pnl + u_pnl
    pnl_tag = f"[{'bold green' if pnl_val > 0 else 'bold red' if pnl_val < 0 else 'yellow'}]{r_pnl:+.2f}[/]"
    unr_tag = f"[{'green' if u_pnl > 0 else 'red' if u_pnl < 0 else 'dim'}]{u_pnl:+.2f}[/]"
    sig_tag = f"[{'bold green' if sig == 'BUY' else 'bold red' if sig == 'SELL' else 'dim yellow'}]{sig:<4}[/]"
    pos_tag = f"[{'bold cyan' if pos else 'dim white'}]{format_position(pos)}[/]"

    line = (
        f"[dim]{session.now()}[/dim] │ "
        f"[bold white]{SYMBOL}[/] [bold cyan]${price:,.2f}[/] │ "
        f"SIG {sig_tag} │ "
        f"POS {pos_tag} │ "
        f"PNL {pnl_tag} (u: {unr_tag}) │ "
        f"TRADES [bold white]{trades}[/] ([cyan]{win_rate:.1f}%[/] WR)"
    )
    console.print(line, markup=True, no_wrap=True, overflow="ignore")

    # Send full telemetry to local web dashboard server
    balance = getattr(session, "starting_balance", 82359.55) + r_pnl + u_pnl
    payload = {
        "symbol": SYMBOL,
        "price": price,
        "signal": sig,
        "realized_pnl": r_pnl,
        "unrealized_pnl": u_pnl,
        "daily_pnl": r_pnl,
        "trade_count": trades,
        "win_count": session.win_count,
        "loss_count": session.loss_count,
        "win_rate": win_rate,
        "total_fees_paid": getattr(fee_tracker, "total_fees", 0.0),
        "position_open": pos is not None,
        "position_size": pos.size if pos else 0.0,
        "entry_price": pos.entry_price if pos else 0.0,
        "balance": balance,
        "starting_balance": getattr(session, "starting_balance", 82359.55),
        "is_bot_running": True,
        "last_trade_pnl": snapshot["last_trade_pnl"],
        "timestamp": session.now(),
    }
    _send_telemetry(payload)


def printer_loop(session: TradingSession, console: Console) -> None:
    last_mtime = 0.0
    state_file = getattr(config, "STATE_FILE", "bot_state.json")
    while not session.stop_event.wait(PRINT_INTERVAL_SECONDS):
        try:
            if os.path.exists(state_file):
                mtime = os.path.getmtime(state_file)
                if mtime > last_mtime:
                    last_mtime = mtime
                    import json
                    with open(state_file, "r", encoding="utf-8") as sf:
                        st = json.load(sf)
                    if st.get("trade_count", 0) == 0 and st.get("realized_pnl", 0.0) == 0.0:
                        with session.lock:
                            if session.trade_count > 0 or session.realized_pnl != 0.0:
                                session.realized_pnl = 0.0
                                session.unrealized_pnl = 0.0
                                session.trade_count = 0
                                session.win_count = 0
                                session.loss_count = 0
                                session.last_trade_pnl = None
                                session.trade_history.clear()
                                console.print("[bold cyan]● STATE RESET DETECTED: Cleared session trade counters to 0.[/bold cyan]")
        except Exception:
            pass
        print_snapshot(session, console)


def run() -> None:
    if not validate_keys():
        return

    order_adapter = BinanceTestnetAdapter(API_KEY, API_SECRET, symbol=SYMBOL)
    websocket_adapter = BinanceWebSocketAdapter(symbol=WS_SYMBOL)
    is_candle_strategy = (_strategy_name != "tick")
    if is_candle_strategy:
        strategy = get_strategy(_strategy_name)
    else:
        strategy = TickMomentumStrategy(
            threshold_pct=THRESHOLD_PCT,
            window_size=WINDOW_SIZE,
            take_profit_pct=TAKE_PROFIT_PCT,
            stop_loss_pct=STOP_LOSS_PCT,
            trailing_stop_pct=TRAILING_STOP_PCT,
        )

    def set_pos_open(val: bool) -> None:
        if hasattr(strategy, "position_open"):
            strategy.position_open = val
        if hasattr(strategy, "_position_open"):
            strategy._position_open = val

    starting_balance = order_adapter.fetch_balance("USDT")
    min_notional = order_adapter.get_min_notional()
    risk = RiskManager(
        starting_balance=starting_balance,
        config=RiskConfig(
            min_seconds_between_trades=MIN_SECONDS_BETWEEN_TRADES,
            min_notional=min_notional,
        ),
    )
    session = TradingSession()
    session.starting_balance = starting_balance if (starting_balance and starting_balance > 0) else 82359.55
    console = Console()
    connection_lock = threading.Lock()
    last_connection_attempt = 0.0

    current_candle = None
    current_candle_start_ms = 0
    tf_str = getattr(config, "ML_TIMEFRAME", "1h")

    if is_candle_strategy:
        console.print(f"[bold cyan]● INITIALIZED STRATEGY:[/] {_strategy_name.upper()} (Trained Quant/ML Engine, {tf_str})")
        try:
            init_candles = order_adapter.fetch_candles(timeframe=tf_str, limit=50)
            if init_candles:
                for c in init_candles[:-1]:
                    strategy.update(c)
                current_candle = init_candles[-1]
                current_candle_start_ms = current_candle.timestamp
                console.print(f"[bold green]● Loaded {len(init_candles)} historical candles. Strategy Inference Active.[/bold green]")
        except Exception as e:
            console.print(f"[yellow]Warning fetching initial candles: {e}[/yellow]")
    else:
        console.print(f"[bold cyan]● INITIALIZED STRATEGY:[/] TICK MOMENTUM (TP={TAKE_PROFIT_PCT}%, SL={STOP_LOSS_PCT}%)")

    # Load persistent state and reconcile against Binance balance
    store = StateStore()
    persisted = store.load()
    if not DRY_RUN:
        persisted = store.reconcile_with_exchange(persisted, order_adapter, base_asset="BTC")

    if persisted.get("open_position"):
        open_pos = persisted["open_position"]
        session.open_position(
            open_pos["entry_price"],
            open_pos["size"],
            open_pos.get("entry_time", session.now(False)),
            entry_fee=float(open_pos.get("entry_fee", open_pos["size"] * open_pos["entry_price"] * 0.001)),
        )
        set_pos_open(True)
        risk.open_positions = 1
        console.print(f"[bold cyan]● RECOVERED POSITION:[/] {open_pos['size']:.6f} BTC @ ${open_pos['entry_price']:.2f}")
    if persisted.get("realized_pnl"):
        session.realized_pnl = float(persisted["realized_pnl"])
        risk.daily_pnl = float(persisted.get("daily_pnl", 0.0))
    if persisted.get("win_count") or persisted.get("loss_count"):
        session.win_count = int(persisted.get("win_count", 0))
        session.loss_count = int(persisted.get("loss_count", 0))

    def handle_tick(tick: dict[str, Any]) -> None:
        try:
            price = float(tick.get("price", 0.0))
            if price <= 0.0:
                return
            now_ms = int(tick.get("timestamp") or (time.time() * 1000))

            if is_candle_strategy:
                nonlocal current_candle, current_candle_start_ms
                tf_seconds = 3600 if tf_str == "1h" else (300 if tf_str == "5m" else 60)
                tf_ms = tf_seconds * 1000

                if current_candle is None or (now_ms - current_candle_start_ms) >= tf_ms:
                    if current_candle is not None:
                        strategy.update(current_candle)
                    current_candle_start_ms = now_ms
                    current_candle = MarketData(
                        open=price,
                        high=price,
                        low=price,
                        close=price,
                        volume=float(tick.get("quantity", 0.0)),
                        timestamp=now_ms,
                    )
                else:
                    current_candle.close = price
                    current_candle.high = max(current_candle.high, price)
                    current_candle.low = min(current_candle.low, price)
                    current_candle.volume += float(tick.get("quantity", 0.0))

                strategy_signal = strategy.decide()

                # Manage SL / TP on open position
                sl_pct = getattr(strategy, "stop_loss", 0.015)
                tp_pct = getattr(strategy, "take_profit", 0.035)
                with session.lock:
                    pos = session.position
                if pos is not None and pos.entry_price > 0:
                    pnl_pct = (price - pos.entry_price) / pos.entry_price
                    if pnl_pct <= -sl_pct or pnl_pct >= tp_pct:
                        strategy_signal = Signal.CLOSE
            else:
                strategy_signal = strategy.on_tick(price)

            display_signal = "SELL" if strategy_signal in (Signal.CLOSE, Signal.SELL) else strategy_signal.value
            session.update_tick(price, display_signal)

            if strategy_signal == Signal.BUY and risk.can_open_position():
                capital = risk.position_size()
                if not risk.check_min_notional(capital):
                    return
                requested_size = capital / price
                if DRY_RUN:
                    sim_fee = requested_size * price * 0.001
                    session.open_position(price, requested_size, session.now(False), entry_fee=sim_fee)
                    risk.open_positions += 1
                    risk.mark_trade_executed()
                    console.print(f"[dim]{session.now(False)}[/dim] [bold green]▲ DRY-RUN BUY[/] @ ${price:.2f} | size={requested_size:.6f}")
                else:
                    try:
                        fill = execute_order(order_adapter, "buy", requested_size, price)
                        session.open_position(fill.fill_price, fill.filled_qty, session.now(False), entry_fee=fill.fee_paid)
                        risk.open_positions += 1
                        risk.mark_trade_executed()
                        persisted["open_position"] = {
                            "entry_price": fill.fill_price,
                            "size": fill.filled_qty,
                            "entry_time": session.now(False),
                            "entry_fee": fill.fee_paid,
                            "side": "long",
                        }
                        try:
                            store.save(persisted)
                        except Exception as se:
                            console.print(f"[yellow]Warning saving state: {se}[/yellow]")
                        console.print(
                            f"[dim]{session.now(False)}[/dim] [bold green]▲ BUY FILLED[/] @ ${fill.fill_price:,.2f} "
                            f"| size={fill.filled_qty:.4f} BTC | fee=${fill.fee_paid:.4f} | #{fill.order_id}"
                        )
                        trade_act = {
                            "timestamp": session.now(False),
                            "action": "BUY",
                            "price": fill.fill_price,
                            "size": fill.filled_qty,
                            "pnl": None,
                            "order_id": str(fill.order_id),
                        }
                        _send_telemetry({
                            "last_action": trade_act,
                            "actions": [trade_act],
                            "position_open": True,
                            "position_size": fill.filled_qty,
                            "entry_price": fill.fill_price,
                            "price": fill.fill_price,
                            "signal": "BUY",
                        })
                    except Exception as error:
                        set_pos_open(False)
                        console.print(f"[bold red]BUY order failed:[/] {error}")

            elif strategy_signal == Signal.CLOSE and risk.can_close_position():
                with session.lock:
                    position = session.position
                if position is None:
                    set_pos_open(False)
                    return
                if DRY_RUN:
                    sim_exit_fee = position.size * price * 0.001
                    trade_pnl = session.close_position(price, session.now(False), exit_fee=sim_exit_fee)
                    risk.record_trade_result(trade_pnl)
                    risk.open_positions -= 1
                    risk.mark_trade_executed()
                    console.print(f"[dim]{session.now(False)}[/dim] [bold red]▼ DRY-RUN SELL[/] @ ${price:.2f} | PnL={trade_pnl:+.2f}")
                else:
                    try:
                        fill = execute_order(order_adapter, "sell", position.size, price)
                        trade_pnl = session.close_position(fill.fill_price, session.now(False), exit_fee=fill.fee_paid)
                        risk.record_trade_result(trade_pnl)
                        risk.open_positions -= 1
                        risk.mark_trade_executed()
                        try:
                            store.record_trade(
                                persisted,
                                entry_price=position.entry_price,
                                exit_price=fill.fill_price,
                                size=position.size,
                                pnl=trade_pnl,
                                fee=fill.fee_paid,
                                entry_time=position.entry_time,
                                exit_time=session.now(False),
                            )
                        except Exception as te:
                            console.print(f"[yellow]Warning recording trade to state: {te}[/yellow]")
                        console.print(
                            f"[dim]{session.now(False)}[/dim] [bold {'green' if trade_pnl >= 0 else 'red'}]▼ SELL FILLED[/] @ ${fill.fill_price:,.2f} "
                            f"| Net PnL={trade_pnl:+.2f} USDT | #{fill.order_id}"
                        )
                        trade_act = {
                            "timestamp": session.now(False),
                            "action": "SELL",
                            "price": fill.fill_price,
                            "size": position.size,
                            "pnl": trade_pnl,
                            "order_id": str(fill.order_id),
                        }
                        _send_telemetry({
                            "last_action": trade_act,
                            "actions": [trade_act],
                            "position_open": False,
                            "position_size": 0.0,
                            "realized_pnl": session.realized_pnl,
                            "price": fill.fill_price,
                            "signal": "SELL",
                        })
                    except Exception as error:
                        set_pos_open(True)
                        console.print(f"[bold red]SELL order failed:[/] {error}")
        except Exception as tick_err:
            console.print(f"[bold red]Tick processing exception:[/] {tick_err}")

    def connect_websocket() -> None:
        nonlocal last_connection_attempt
        with connection_lock:
            last_connection_attempt = time.monotonic()
            websocket_adapter.start(on_tick=handle_tick)

    def reconnect_loop() -> None:
        while not session.stop_event.wait(RECONNECT_CHECK_SECONDS):
            with connection_lock:
                websocket = websocket_adapter.ws
                connection_age = time.monotonic() - last_connection_attempt
            if websocket is None:
                continue
            socket = websocket.sock
            if socket is None or not socket.connected:
                if connection_age < RECONNECT_CHECK_SECONDS:
                    continue
                print(f"[{session.now(False)}] WebSocket disconnected; attempting reconnection...")
                connect_websocket()

    print(f"Starting REAL-TIME bot on {SYMBOL} | balance: {starting_balance:.2f} USDT")
    print("Connecting to live tick stream... (Ctrl+C to stop)")
    printer_thread = threading.Thread(target=printer_loop, args=(session, console), name="dashboard-printer")
    reconnect_thread = threading.Thread(target=reconnect_loop, name="websocket-reconnector")
    try:
        printer_thread.start()
        connect_websocket()
        reconnect_thread.start()
        while not session.stop_event.wait(0.5):
            pass
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        session.stop_event.set()
        websocket_adapter.stop()
        printer_thread.join(timeout=2.0)
        reconnect_thread.join(timeout=2.0)
        print_session_summary(session)


def print_session_summary(session: TradingSession) -> None:
    with session.lock:
        closed_trades = session.win_count + session.loss_count
        win_rate = session.win_count / closed_trades * 100 if closed_trades else 0.0
        largest_win = max((trade.pnl for trade in session.trade_history), default=0.0)
        largest_loss = min((trade.pnl for trade in session.trade_history), default=0.0)
        duration = time.monotonic() - session.started_at
        trade_count = session.trade_count
        realized_pnl = session.realized_pnl

    print("\nFINAL SESSION SUMMARY")
    print(f"Total trades executed: {trade_count}")
    print(f"Total realized P&L: {realized_pnl:+.2f} USDT")
    print(f"Win rate: {win_rate:.1f}%")
    print(f"Session duration: {duration:.1f} seconds")
    print(f"Largest single win: {largest_win:+.2f} USDT")
    print(f"Largest single loss: {largest_loss:+.2f} USDT")


if __name__ == "__main__":
    run()
