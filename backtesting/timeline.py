"""
backtesting/timeline.py — Chronological timeline and rebalancing cadence generator.

Manages simulation steps, calendar boundaries, and discrete rebalance event scheduling
with zero look-ahead.
"""
from __future__ import annotations

from typing import List, Sequence, Union
import pandas as pd


class BacktestTimeline:
    """
    Generates and manages the ordered simulation timeline for the backtest engine.
    """

    def __init__(
        self,
        trading_dates: Sequence[Union[str, pd.Timestamp]],
        rebalance_frequency: str = "weekly",
        start_date: Optional[Union[str, pd.Timestamp]] = None,
        end_date: Optional[Union[str, pd.Timestamp]] = None,
        warmup_bars: int = 0,
    ) -> None:
        """
        Initialize the simulation timeline.

        Parameters:
            trading_dates: Sequence of timestamps representing market trading sessions.
            rebalance_frequency: 'daily', 'weekly', 'biweekly', 'monthly', or integer step.
            start_date: Optional start date filter.
            end_date: Optional end date filter.
            warmup_bars: Number of initial bars reserved for feature/covariance warmup.
        """
        # Clean and sort unique timestamps
        ts_series = pd.to_datetime(pd.Series(list(trading_dates))).drop_duplicates().sort_values().reset_index(drop=True)
        if not ts_series.empty:
            tz = ts_series.dt.tz
            if start_date is not None:
                st = pd.to_datetime(start_date)
                if tz is not None and st.tzinfo is None:
                    st = st.tz_localize(tz)
                elif tz is None and st.tzinfo is not None:
                    st = st.tz_localize(None)
                ts_series = ts_series[ts_series >= st]
            if end_date is not None:
                et = pd.to_datetime(end_date)
                if tz is not None and et.tzinfo is None:
                    et = et.tz_localize(tz)
                elif tz is None and et.tzinfo is not None:
                    et = et.tz_localize(None)
                ts_series = ts_series[ts_series <= et]

        self.all_dates: List[pd.Timestamp] = ts_series.tolist()
        self.rebalance_frequency = rebalance_frequency
        self.warmup_bars = warmup_bars
        self.rebalance_dates: List[pd.Timestamp] = self._schedule_rebalance_dates()

    def _schedule_rebalance_dates(self) -> List[pd.Timestamp]:
        """Identify which simulation timestamps trigger portfolio rebalancing."""
        if not self.all_dates:
            return []

        # Available simulation dates after warmup
        active_dates = self.all_dates[self.warmup_bars:] if len(self.all_dates) > self.warmup_bars else self.all_dates

        if not active_dates:
            return []

        freq = str(self.rebalance_frequency).lower()
        rebal_dates: List[pd.Timestamp] = []

        if freq == "daily":
            rebal_dates = list(active_dates)
        elif freq == "weekly":
            # Rebalance on the first trading session of each ISO week
            last_week = None
            for dt in active_dates:
                curr_week = (dt.year, dt.isocalendar().week)
                if curr_week != last_week:
                    rebal_dates.append(dt)
                    last_week = curr_week
        elif freq == "biweekly":
            # Rebalance every 10 trading sessions
            for i, dt in enumerate(active_dates):
                if i % 10 == 0:
                    rebal_dates.append(dt)
        elif freq == "monthly":
            # Rebalance on the first trading session of each calendar month
            last_month = None
            for dt in active_dates:
                curr_month = (dt.year, dt.month)
                if curr_month != last_month:
                    rebal_dates.append(dt)
                    last_month = curr_month
        elif freq.isdigit():
            step = max(1, int(freq))
            for i, dt in enumerate(active_dates):
                if i % step == 0:
                    rebal_dates.append(dt)
        else:
            # Default to weekly
            last_week = None
            for dt in active_dates:
                curr_week = (dt.year, dt.isocalendar().week)
                if curr_week != last_week:
                    rebal_dates.append(dt)
                    last_week = curr_week

        return rebal_dates

    def is_rebalance_date(self, timestamp: pd.Timestamp) -> bool:
        """Check whether the given timestamp is an active rebalance date."""
        return timestamp in set(self.rebalance_dates)

    def get_step_count(self) -> int:
        """Total number of simulation steps."""
        return len(self.all_dates)

    def __iter__(self):
        return iter(self.all_dates)

    def __len__(self):
        return len(self.all_dates)
