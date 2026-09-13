"""
core/strategies/macd_strategy.py

MACD (Moving Average Convergence Divergence) Strategy.

MACD tracks two exponential moving averages and their difference:
- MACD line  = EMA(fast) - EMA(slow)
- Signal line = EMA(MACD line, signal_period)
- Histogram   = MACD - Signal

Trading rules:
- MACD line crosses ABOVE signal line → BUY (bullish momentum)
- MACD line crosses BELOW signal line → CLOSE (bearish momentum)

MACD is excellent in trending markets. It smooths out noise better than
a simple SMA crossover because it uses exponential weighting.
"""

from core.strategy import Strategy, Signal, MarketData


class MACDStrategy(Strategy):
    """
    MACD crossover strategy.

    Parameters:
        fast_period   — fast EMA window (default 12)
        slow_period   — slow EMA window (default 26)
        signal_period — signal line EMA window (default 9)
    """

    def __init__(self, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9):
        super().__init__(name="MACD")
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period
        self._macd_history: list[float] = []
        self._position_open = False

    @staticmethod
    def _ema(values: list[float], period: int) -> float:
        """Calculate EMA for the last N values using the smoothing formula."""
        if len(values) < period:
            return sum(values) / len(values)
        k = 2.0 / (period + 1.0)
        ema = sum(values[:period]) / period
        for v in values[period:]:
            ema = v * k + ema * (1.0 - k)
        return ema

    def update(self, candle: MarketData) -> Signal:
        self.history.append(candle)

        if len(self.history) >= self.slow_period:
            window = min(len(self.history), self.slow_period * 5)
            closes = [c.close for c in self.history[-window:]]
            fast = self._ema(closes, self.fast_period)
            slow = self._ema(closes, self.slow_period)
            self._macd_history.append(fast - slow)

        return self.decide()


    def decide(self) -> Signal:
        if len(self._macd_history) < self.signal_period + 1:
            return Signal.HOLD

        window = min(len(self._macd_history), self.signal_period * 5)
        recent_macd = self._macd_history[-window:]
        signal_line = self._ema(recent_macd, self.signal_period)
        prev_signal = self._ema(recent_macd[:-1], self.signal_period)
        current_macd = self._macd_history[-1]
        prev_macd = self._macd_history[-2]



        crossed_above = prev_macd <= prev_signal and current_macd > signal_line
        crossed_below = prev_macd >= prev_signal and current_macd < signal_line

        if crossed_above and not self._position_open:
            self._position_open = True
            return Signal.BUY

        if crossed_below and self._position_open:
            self._position_open = False
            return Signal.CLOSE

        return Signal.HOLD
