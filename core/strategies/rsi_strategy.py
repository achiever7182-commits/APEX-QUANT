"""
core/strategies/rsi_strategy.py

RSI (Relative Strength Index) Strategy.

RSI measures how overbought or oversold a market is on a 0–100 scale.
- RSI < oversold_level  → market is cheap → BUY signal
- RSI > overbought_level → market is expensive → CLOSE signal

RSI is one of the most widely used and battle-tested technical indicators,
particularly effective in ranging (sideways) markets.
"""

from core.strategy import Strategy, Signal, MarketData


class RSIStrategy(Strategy):
    """
    RSI mean-reversion strategy.

    Parameters:
        period       — lookback window for RSI calculation (default 14)
        oversold     — RSI level below which we consider buying (default 30)
        overbought   — RSI level above which we consider closing (default 70)
    """

    def __init__(self, period: int = 14, oversold: float = 30.0, overbought: float = 70.0):
        super().__init__(name="RSI")
        self.period = period
        self.oversold = oversold
        self.overbought = overbought
        self._position_open = False

    def _compute_rsi(self) -> float | None:
        """Calculate RSI from the price history. Returns None if not enough data."""
        if len(self.history) < self.period + 1:
            return None

        closes = [c.close for c in self.history[-(self.period + 1):]]
        gains, losses = [], []
        for i in range(1, len(closes)):
            delta = closes[i] - closes[i - 1]
            gains.append(max(delta, 0.0))
            losses.append(max(-delta, 0.0))

        avg_gain = sum(gains) / self.period
        avg_loss = sum(losses) / self.period

        if avg_loss == 0.0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    def decide(self) -> Signal:
        rsi = self._compute_rsi()
        if rsi is None:
            return Signal.HOLD

        if not self._position_open and rsi < self.oversold:
            self._position_open = True
            return Signal.BUY

        if self._position_open and rsi > self.overbought:
            self._position_open = False
            return Signal.CLOSE

        return Signal.HOLD
