"""Tick-driven Binance testnet trader with a scrolling terminal dashboard.

Run with:
    python main_realtime.py      # standalone
    python run.py realtime       # via unified launcher

The websocket supplies every trade tick. A separate printer thread emits one
snapshot per second so the terminal keeps readable scrollback even when the
market is quiet or no trade is triggered.
"""

from __future__ import annotations

import sys
import threading
import time
from dataclasses import dataclass
from typing import Any

from rich.console import Console
from rich.style import Style

from adapters.binance_adapter import BinanceTestnetAdapter
from adapters.binance_websocket_adapter import BinanceWebSocketAdapter
from core.risk_manager import RiskConfig, RiskManager
from core.strategy import Signal
from core.tick_strategy import TickMomentumStrategy
from core.strategies import list_strategies
from core.execution import execute_order, fee_tracker
from state.store import StateStore
from config import (
    API_KEY, API_SECRET, SYMBOL, WS_SYMBOL,
    PRINT_INTERVAL_SECONDS, RECONNECT_CHECK_SECONDS,
    THRESHOLD_PCT, WINDOW_SIZE, MIN_SECONDS_BETWEEN_TRADES,
    DRY_RUN, validate_keys,
)
from utils import order_fill_price


_strategy_name: str = "tick"


def set_strategy(name: str) -> None:
    """Validate and set strategy for realtime mode."""
    global _strategy_name
    name = name.lower()
    if name in ("tick", "momentum", "tick_momentum"):
        _strategy_name = "tick"
    elif name in list_strategies():
        print(
            f"[realtime] Error: '{name}' is a candle-based strategy.\n"
            f"This mode only supports tick-based strategies (e.g. 'tick').\n"
            f"Use polling mode for {name.upper()}:\n"
            f"    python run.py polling --strategy {name}"
        )
        sys.exit(1)
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
    line = (
        f"[{session.now()}] price={snapshot['price']:.2f} | "
        f"signal={snapshot['signal']:<5} | "
        f"position={format_position(snapshot['position'])} | "
        f"realized_PnL={snapshot['realized_pnl']:+.2f} | "
        f"unrealized_PnL={snapshot['unrealized_pnl']:+.2f} | "
        f"trades={snapshot['trade_count']} | "
        f"win_rate={snapshot['win_rate']:.1f}%"
    )
    last_trade_pnl = snapshot["last_trade_pnl"]
    if snapshot["unrealized_pnl"] < 0 or (last_trade_pnl is not None and last_trade_pnl < 0):
        style = Style(color="red")
    elif snapshot["unrealized_pnl"] > 0 or (last_trade_pnl is not None and last_trade_pnl > 0):
        style = Style(color="green")
    else:
        style = Style(color="yellow")
    console.print(line, style=style, markup=False, no_wrap=True, overflow="ignore")


def printer_loop(session: TradingSession, console: Console) -> None:
    while not session.stop_event.wait(PRINT_INTERVAL_SECONDS):
        print_snapshot(session, console)


def run() -> None:
    if not validate_keys():
        return

    order_adapter = BinanceTestnetAdapter(API_KEY, API_SECRET, symbol=SYMBOL)
    websocket_adapter = BinanceWebSocketAdapter(symbol=WS_SYMBOL)
    strategy = TickMomentumStrategy(threshold_pct=THRESHOLD_PCT, window_size=WINDOW_SIZE)
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
    console = Console()
    connection_lock = threading.Lock()
    last_connection_attempt = 0.0

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
        strategy.position_open = True
        risk.open_positions = 1
        print(f"[state] Position active: {open_pos['size']:.6f} BTC @ {open_pos['entry_price']:.2f} USDT")
    if persisted.get("realized_pnl"):
        session.realized_pnl = float(persisted["realized_pnl"])
        risk.daily_pnl = float(persisted.get("daily_pnl", 0.0))
    if persisted.get("win_count") or persisted.get("loss_count"):
        session.win_count = int(persisted.get("win_count", 0))
        session.loss_count = int(persisted.get("loss_count", 0))

    def handle_tick(tick: dict[str, Any]) -> None:
        price = float(tick["price"])
        strategy_signal = strategy.on_tick(price)
        display_signal = "SELL" if strategy_signal == Signal.CLOSE else strategy_signal.value
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
                print(f"[{session.now(False)}] DRY-RUN BUY executed at {price:.2f} | size={requested_size:.6f} | fee={sim_fee:.4f}")
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
                    store.save(persisted)
                    print(
                        f"[{session.now(False)}] BUY executed at {fill.fill_price:.2f} ({fill.method}) "
                        f"| fee={fill.fee_paid:.4f} | order={fill.order_id}"
                    )
                except Exception as error:
                    # The strategy flips its internal flag before returning BUY. Put
                    # it back so an order failure does not create a phantom position.
                    strategy.position_open = False
                    print(f"[{session.now(False)}] BUY order failed: {error}")

        elif strategy_signal == Signal.CLOSE and risk.can_close_position():
            with session.lock:
                position = session.position
            if position is None:
                strategy.position_open = False
                return
            if DRY_RUN:
                sim_exit_fee = position.size * price * 0.001
                trade_pnl = session.close_position(price, session.now(False), exit_fee=sim_exit_fee)
                risk.record_trade_result(trade_pnl)
                risk.open_positions -= 1
                risk.mark_trade_executed()
                print(
                    f"[{session.now(False)}] DRY-RUN SELL executed at {price:.2f} "
                    f"| Net P&L={trade_pnl:+.2f} USDT (fees: {position.entry_fee + sim_exit_fee:.4f})"
                )
            else:
                try:
                    fill = execute_order(order_adapter, "sell", position.size, price)
                    trade_pnl = session.close_position(fill.fill_price, session.now(False), exit_fee=fill.fee_paid)
                    risk.record_trade_result(trade_pnl)
                    risk.open_positions -= 1
                    risk.mark_trade_executed()
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
                    print(
                        f"[{session.now(False)}] SELL executed at {fill.fill_price:.2f} ({fill.method}) "
                        f"| Net P&L={trade_pnl:+.2f} USDT (total fees: {position.entry_fee + fill.fee_paid:.4f}) | order={fill.order_id}"
                    )
                except Exception as error:
                    # Keep both local and strategy state open until a sell is confirmed.
                    strategy.position_open = True
                    print(f"[{session.now(False)}] SELL order failed: {error}")

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
