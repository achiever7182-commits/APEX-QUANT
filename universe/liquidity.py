"""
universe/liquidity.py — Quantitative Liquidity and Turnover Engine for Indian Equities.

Calculates rolling median daily turnover, volume characteristics, and session continuity
using Step 2 market data models.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Union
import numpy as np
import pandas as pd

from data.market.models import MarketBar


@dataclass(frozen=True)
class LiquidityMetrics:
    """Quantitative liquidity profile for an equity over a lookback window."""
    symbol: str
    lookback_bars: int
    median_turnover: float       # 20-day median turnover in INR (e.g. ₹50,000,000)
    mean_turnover: float         # 20-day average turnover in INR
    median_volume: float         # 20-day median share volume
    valid_sessions: int          # Actual traded bars in window
    missing_percentage: float    # Percentage of expected bars missing (0.0 to 1.0)
    last_close: float            # Most recent closing price in window


class LiquidityEngine:
    """
    Computes liquidity metrics from historical price/volume data.
    """

    @classmethod
    def calculate_metrics(
        cls,
        symbol: str,
        data: Union[pd.DataFrame, List[MarketBar]],
        lookback_bars: int = 20,
        expected_bars: Optional[int] = None,
    ) -> LiquidityMetrics:
        """
        Calculate liquidity and turnover metrics over the trailing lookback period.
        
        Args:
            symbol: Ticker symbol
            data: DataFrame with ['close', 'volume'] or list of MarketBar objects
            lookback_bars: Rolling window size (default 20 trading days)
            expected_bars: Expected trading days in window (default equal to lookback_bars)
        """
        clean_sym = symbol.upper().replace(".NS", "").strip()

        if isinstance(data, list):
            if not data:
                return cls._empty_metrics(clean_sym, lookback_bars)
            records = [{"close": b.close, "volume": b.volume, "turnover": b.turnover} for b in data]
            df = pd.DataFrame(records)
        elif isinstance(data, pd.DataFrame):
            if data.empty:
                return cls._empty_metrics(clean_sym, lookback_bars)
            df = data.copy()
        else:
            raise TypeError(f"Unsupported data type: {type(data)}")

        # Use the most recent lookback_bars
        recent = df.tail(lookback_bars).copy()
        valid_sessions = len(recent)

        if valid_sessions == 0:
            return cls._empty_metrics(clean_sym, lookback_bars)

        # Calculate turnover: use 'turnover' column if populated and non-zero, else close * volume
        if "turnover" in recent.columns and (recent["turnover"] > 0).any():
            turnover_series = recent["turnover"]
        else:
            turnover_series = recent["close"] * recent["volume"]

        med_turnover = float(turnover_series.median())
        mean_turnover = float(turnover_series.mean())
        med_volume = float(recent["volume"].median())
        last_close = float(recent["close"].iloc[-1])

        exp_bars = expected_bars if expected_bars is not None else lookback_bars
        missing_count = max(0, exp_bars - valid_sessions)
        missing_pct = float(missing_count / exp_bars) if exp_bars > 0 else 0.0

        return LiquidityMetrics(
            symbol=clean_sym,
            lookback_bars=lookback_bars,
            median_turnover=med_turnover,
            mean_turnover=mean_turnover,
            median_volume=med_volume,
            valid_sessions=valid_sessions,
            missing_percentage=missing_pct,
            last_close=last_close,
        )

    @classmethod
    def _empty_metrics(cls, symbol: str, lookback: int) -> LiquidityMetrics:
        return LiquidityMetrics(
            symbol=symbol,
            lookback_bars=lookback,
            median_turnover=0.0,
            mean_turnover=0.0,
            median_volume=0.0,
            valid_sessions=0,
            missing_percentage=1.0,
            last_close=0.0,
        )
