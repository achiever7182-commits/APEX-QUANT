"""
core/tick_strategy.py

A strategy designed for live tick data (not minute candles). Reacts to every
price update, but decides based on how much price has moved from a rolling
baseline -- actively buying on momentum breakouts, taking profit on rallies,
cutting losses with stop-loss, and holding in between.
"""

from collections import deque
import time
from core.strategy import Signal


class TickMomentumStrategy:
    """
    Watches live ticks with a rolling window.
    - BUY: when price surges above recent rolling average by `threshold_pct`.
    - CLOSE: takes profit on rally (`take_profit_pct`), cuts loss on drop (`stop_loss_pct`),
      locks in profit via trailing stop if price peaks and reverses, or exits stale positions.
    - HOLD: when inside normal volatility bands.
    """

    def __init__(
        self,
        threshold_pct: float = 0.08,
        take_profit_pct: float | None = None,
        stop_loss_pct: float | None = None,
        trailing_stop_pct: float | None = None,
        window_size: int = 30,
        max_hold_seconds: float = 300.0,
    ):
        self.threshold_pct = threshold_pct / 100.0
        self.take_profit_pct = (take_profit_pct or threshold_pct) / 100.0
        self.stop_loss_pct = (stop_loss_pct or threshold_pct) / 100.0
        self.trailing_stop_pct = (trailing_stop_pct or (threshold_pct * 0.5)) / 100.0
        self.window_size = window_size
        self.max_hold_seconds = max_hold_seconds
        self.window: deque[float] = deque(maxlen=window_size)
        self.reference_price: float | None = None
        self.entry_price: float | None = None
        self.entry_time: float | None = None
        self.peak_price: float | None = None
        self.position_open: bool = False

    def set_open_position(self, entry_price: float, entry_time: str | float | None = None):
        """Restore position state from StateStore on startup or after BUY fill."""
        self.position_open = True
        self.entry_price = float(entry_price)
        self.reference_price = float(entry_price)
        self.peak_price = float(entry_price)
        if isinstance(entry_time, (int, float)):
            self.entry_time = float(entry_time)
        else:
            # If loaded from an older session, allow immediate exit evaluation
            self.entry_time = time.time() - 300.0

    def reset_position(self):
        """Clear position tracking when flat."""
        self.position_open = False
        self.entry_price = None
        self.entry_time = None
        self.peak_price = None

    def on_tick(self, price: float) -> Signal:
        self.window.append(price)

        if len(self.window) < 5:
            return Signal.HOLD

        rolling_avg = sum(self.window) / len(self.window)

        # ── 1. If currently in a position, actively manage the exit ──
        if self.position_open:
            if not self.entry_price:
                self.entry_price = self.reference_price or price

            if self.peak_price is None or price > self.peak_price:
                self.peak_price = price

            pnl_pct = (price - self.entry_price) / self.entry_price
            peak_gain = (self.peak_price - self.entry_price) / self.entry_price
            drawdown_from_peak = (self.peak_price - price) / self.peak_price if self.peak_price else 0.0

            # A. Take Profit: Hit profit target
            if pnl_pct >= self.take_profit_pct:
                self.reset_position()
                return Signal.CLOSE

            # B. Trailing Stop: lock in profit if price made a run and retraces
            if peak_gain >= (self.take_profit_pct * 0.6) and drawdown_from_peak >= self.trailing_stop_pct:
                self.reset_position()
                return Signal.CLOSE

            # C. Stop Loss: cut adverse trade
            if pnl_pct <= -self.stop_loss_pct:
                self.reset_position()
                return Signal.CLOSE

            # D. Momentum Reversal: price drops below rolling average while in profit
            if pnl_pct > 0 and price < rolling_avg:
                self.reset_position()
                return Signal.CLOSE

            # E. Stale hold timeout: if held for too long and price is at/above breakeven
            if self.entry_time and (time.time() - self.entry_time > self.max_hold_seconds) and pnl_pct >= 0:
                self.reset_position()
                return Signal.CLOSE

            return Signal.HOLD

        # ── 2. If NOT in a position, scan for momentum breakout to BUY ──
        momentum = (price - rolling_avg) / rolling_avg

        if momentum >= self.threshold_pct:
            self.position_open = True
            self.entry_price = price
            self.entry_time = time.time()
            self.peak_price = price
            self.reference_price = price
            return Signal.BUY

        return Signal.HOLD
