"""
core/strategies/ema_crossover_strategy.py

EMA Crossover Strategy.

Like the SMA crossover but uses Exponential Moving Averages, which weight
recent prices more heavily. This makes the strategy react faster to new
trends while still filtering out short-term noise.

Trading rules:
- Short EMA crosses ABOVE long EMA → BUY (trend turning up)
- Short EMA crosses BELOW long EMA → CLOSE (trend turning down)

Faster response than SMA means fewer missed entries, but slightly more
false signals in choppy markets. Adjust fast/slow windows to taste.
"""

from core.strategy import Strategy, Signal, MarketData


class EMACrossoverStrategy(Strategy):
    """
    EMA crossover strategy.

    Parameters:
        fast_period — short EMA window (default 9)
        slow_period — long EMA window (default 21)
    """

    def __init__(self, fast_period: int = 9, slow_period: int = 21):
        super().__init__(name="EMA_Crossover")
        self.fast_period = fast_period
        self.slow_period = slow_period
        self._position_open = False

    @staticmethod
    def _ema(closes: list[float], period: int) -> float:
        k = 2.0 / (period + 1.0)
        ema = sum(closes[:period]) / period
        for price in closes[period:]:
            ema = price * k + ema * (1.0 - k)
        return ema

    def decide(self) -> Signal:
        if len(self.history) < self.slow_period + 1:
            return Signal.HOLD

        # Window of 5x slow_period provides full exponential smoothing convergence
        window = min(len(self.history), self.slow_period * 5)
        closes = [c.close for c in self.history[-window:]]
        fast_now = self._ema(closes, self.fast_period)
        slow_now = self._ema(closes, self.slow_period)


        closes_prev = closes[:-1]
        fast_prev = self._ema(closes_prev, self.fast_period)
        slow_prev = self._ema(closes_prev, self.slow_period)

        crossed_above = fast_prev <= slow_prev and fast_now > slow_now
        crossed_below = fast_prev >= slow_prev and fast_now < slow_now

        if crossed_above and not self._position_open:
            self._position_open = True
            return Signal.BUY

        if crossed_below and self._position_open:
            self._position_open = False
            return Signal.CLOSE

        return Signal.HOLD
