"""
universe/liquidity.py — Quantitative Liquidity and Turnover Engine for Indian Equities.

Calculates rolling median daily turnover, volume characteristics, and session continuity
using Step 2 market data models.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import List, Optional, Union
import numpy as np
import pandas as pd

from data.market.calendar import NSEMarketCalendar
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
        calendar: Optional[NSEMarketCalendar] = None,
        as_of_date: Optional[Union[date, datetime, str]] = None,
    ) -> LiquidityMetrics:
        """
        Calculate liquidity and turnover metrics over the trailing lookback period.
        
        Args:
            symbol: Ticker symbol
            data: DataFrame with ['close', 'volume'] or list of MarketBar objects
            lookback_bars: Rolling window size (default 20 trading days)
            expected_bars: Expected trading days in window (default equal to lookback_bars)
            calendar: Optional NSEMarketCalendar instance for trading session verification
            as_of_date: Optional point-in-time cutoff date to prevent future lookahead
        """
        clean_sym = symbol.upper().replace(".NS", "").strip()

        if isinstance(data, list):
            if not data:
                return cls._empty_metrics(clean_sym, lookback_bars)
            records = [
                {
                    "timestamp": b.timestamp,
                    "close": b.close,
                    "volume": b.volume,
                    "turnover": b.turnover,
                }
                for b in data
            ]
            df = pd.DataFrame(records)
        elif isinstance(data, pd.DataFrame):
            if data.empty:
                return cls._empty_metrics(clean_sym, lookback_bars)
            df = data.copy()
        else:
            raise TypeError(f"Unsupported data type: {type(data)}")

        cal = calendar or NSEMarketCalendar()

        # Identify timestamp column if available
        ts_col: Optional[str] = None
        for candidate in ["timestamp", "date", "datetime", "Date", "Timestamp"]:
            if candidate in df.columns:
                ts_col = candidate
                break

        if ts_col is not None:
            parsed_ts = pd.to_datetime(df[ts_col], errors="coerce")
            valid_ts = ~parsed_ts.isna()
            if valid_ts.any():
                df = df[valid_ts].copy()
                parsed_ts = parsed_ts[valid_ts]

                # Prevent future-data leakage if as_of_date is provided
                if as_of_date is not None:
                    target_date = cal._to_date(as_of_date)
                    date_mask = parsed_ts.dt.date <= target_date
                    df = df[date_mask].copy()
                    parsed_ts = parsed_ts[date_mask]
                    if df.empty:
                        return cls._empty_metrics(clean_sym, lookback_bars)

                # Ensure strict chronological sorting
                df = df.assign(_sort_ts=parsed_ts).sort_values("_sort_ts").drop(columns=["_sort_ts"]).reset_index(drop=True)
        elif isinstance(df.index, pd.DatetimeIndex):
            if as_of_date is not None:
                target_date = cal._to_date(as_of_date)
                df = df[df.index.date <= target_date].copy()
                if df.empty:
                    return cls._empty_metrics(clean_sym, lookback_bars)
            df = df.sort_index().reset_index()

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

        baseline_exp = expected_bars if expected_bars is not None else lookback_bars

        # Check calendar gaps when timestamps are available
        actual_dates = set()
        if ts_col is not None and ts_col in recent.columns:
            recent_ts = pd.to_datetime(recent[ts_col], errors="coerce")
            actual_dates = set(recent_ts.dropna().dt.date)
        elif isinstance(recent.index, pd.DatetimeIndex):
            actual_dates = set(recent.index.date)

        if actual_dates:
            start_date = min(actual_dates)
            end_date = max(actual_dates)
            if as_of_date is not None:
                as_of_d = cal._to_date(as_of_date)
                if as_of_d > end_date:
                    end_date = as_of_d

            missing_days = cal.get_missing_trading_days(actual_dates, start_date=start_date, end_date=end_date)
            cal_missing_count = len(missing_days)

            total_expected = max(baseline_exp, valid_sessions + cal_missing_count)
            missing_count = total_expected - valid_sessions
            missing_pct = float(missing_count / total_expected) if total_expected > 0 else 0.0
        else:
            missing_count = max(0, baseline_exp - valid_sessions)
            missing_pct = float(missing_count / baseline_exp) if baseline_exp > 0 else 0.0

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
