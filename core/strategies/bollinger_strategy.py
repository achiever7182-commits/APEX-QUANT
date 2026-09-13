"""
core/strategies/bollinger_strategy.py

Bollinger Band Mean-Reversion Strategy.

Bollinger Bands define a dynamic price channel around a moving average:
- Upper Band = SMA + (std_dev * multiplier)
- Lower Band = SMA - (std_dev * multiplier)

~95% of price action stays within 2 standard deviations. When price touches
a band edge, it tends to revert toward the middle. This is "mean reversion."

Trading rules:
- Price touches or breaks BELOW the lower band → BUY (oversold)
- Price touches or breaks ABOVE the upper band → CLOSE (overbought)

Bollinger Bands work best in ranging (non-trending) markets.
"""

import math
from core.strategy import Strategy, Signal, MarketData


class BollingerStrategy(Strategy):
    """
    Bollinger Band mean-reversion strategy.

    Parameters:
        period     — SMA window and std dev lookback (default 20)
        multiplier — how many std devs define the bands (default 2.0)
    """

    def __init__(self, period: int = 20, multiplier: float = 2.0):
        super().__init__(name="Bollinger")
        self.period = period
        self.multiplier = multiplier
        self._position_open = False

    def _bands(self) -> tuple[float, float, float] | None:
        """Returns (upper, middle, lower) bands. None if not enough data."""
        if len(self.history) < self.period:
            return None
        closes = [c.close for c in self.history[-self.period:]]
        sma = sum(closes) / self.period
        variance = sum((x - sma) ** 2 for x in closes) / self.period
        std = math.sqrt(variance)
        return (sma + self.multiplier * std, sma, sma - self.multiplier * std)

    def decide(self) -> Signal:
        bands = self._bands()
        if bands is None:
            return Signal.HOLD

        upper, _, lower = bands
        price = self.history[-1].close

        if not self._position_open and price <= lower:
            self._position_open = True
            return Signal.BUY

        if self._position_open and price >= upper:
            self._position_open = False
            return Signal.CLOSE

        return Signal.HOLD
