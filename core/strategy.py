"""
core/strategy.py

Every trading strategy plugs into the bot by implementing this interface.
This keeps the "brain" of the bot separate from WHICH market it's trading on
(crypto, forex, stocks) -- the same strategy can run on any adapter.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


class Signal(Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    CLOSE = "CLOSE"


@dataclass
class MarketData:
    """A single price snapshot passed to the strategy on every tick/candle."""
    symbol: str
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float


class Strategy(ABC):
    """Base class for all strategies. Subclass this and implement decide()."""

    def __init__(self, name: str):
        self.name = name
        self.history: list[MarketData] = []

    def update(self, candle: MarketData) -> Signal:
        """Called by the engine on every new candle. Stores history, then decides."""
        self.history.append(candle)
        return self.decide()

    @abstractmethod
    def decide(self) -> Signal:
        """Look at self.history and return a Signal. Implement your logic here."""
        raise NotImplementedError


class SMACrossoverStrategy(Strategy):
    """
    Example starter strategy: Simple Moving Average crossover.
    BUY when short-term average crosses above long-term average.
    SELL when it crosses below.
    This is intentionally simple -- swap it out once you have your own logic.
    """

    def __init__(self, short_window: int = 9, long_window: int = 21):
        super().__init__(name="SMA_Crossover")
        self.short_window = short_window
        self.long_window = long_window
        self._position_open = False

    def decide(self) -> Signal:
        if len(self.history) < self.long_window:
            return Signal.HOLD  # not enough data yet

        recent = self.history[-(self.long_window + 1):]
        closes = [c.close for c in recent]
        short_avg = sum(closes[-self.short_window:]) / self.short_window
        long_avg = sum(closes[-self.long_window:]) / self.long_window


        prev_closes = closes[:-1]
        if len(prev_closes) >= self.long_window:
            prev_short = sum(prev_closes[-self.short_window:]) / self.short_window
            prev_long = sum(prev_closes[-self.long_window:]) / self.long_window
        else:
            prev_short, prev_long = short_avg, long_avg

        crossed_up = prev_short <= prev_long and short_avg > long_avg
        crossed_down = prev_short >= prev_long and short_avg < long_avg

        if crossed_up and not self._position_open:
            self._position_open = True
            return Signal.BUY
        elif crossed_down and self._position_open:
            self._position_open = False
            return Signal.CLOSE

        return Signal.HOLD
