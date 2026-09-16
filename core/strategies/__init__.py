"""
core/strategies — All available candle-based strategies.

Usage:
    from core.strategies import get_strategy, list_strategies

    strategy = get_strategy("rsi")           # default params
    strategy = get_strategy("macd", fast_period=8, slow_period=21)
"""

from core.strategy import SMACrossoverStrategy
from core.strategies.rsi_strategy import RSIStrategy
from core.strategies.macd_strategy import MACDStrategy
from core.strategies.bollinger_strategy import BollingerStrategy
from core.strategies.ema_crossover_strategy import EMACrossoverStrategy
from core.strategies.ml_strategy import MLStrategy

# Registry: name → (class, default_kwargs)
_REGISTRY: dict[str, tuple] = {
    "sma":       (SMACrossoverStrategy,  {"short_window": 9, "long_window": 21}),
    "ema":       (EMACrossoverStrategy,  {"fast_period": 9, "slow_period": 21}),
    "rsi":       (RSIStrategy,           {"period": 14, "oversold": 30.0, "overbought": 70.0}),
    "macd":      (MACDStrategy,          {"fast_period": 12, "slow_period": 26, "signal_period": 9}),
    "bollinger": (BollingerStrategy,     {"period": 20, "multiplier": 2.0}),
    "ml":        (MLStrategy,            {"min_confidence": 0.60}),
}


def get_strategy(name: str, **kwargs):
    """Return an instantiated strategy by name. kwargs override default params."""
    name = name.lower()
    if name not in _REGISTRY:
        raise ValueError(f"Unknown strategy '{name}'. Available: {list_strategies()}")
    cls, defaults = _REGISTRY[name]
    params = {**defaults, **kwargs}
    return cls(**params)


def list_strategies() -> list[str]:
    """Return a sorted list of registered strategy names."""
    return sorted(_REGISTRY.keys())


__all__ = [
    "get_strategy",
    "list_strategies",
    "SMACrossoverStrategy",
    "EMACrossoverStrategy",
    "RSIStrategy",
    "MACDStrategy",
    "BollingerStrategy",
    "MLStrategy",
]

