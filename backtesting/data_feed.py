"""
backtesting/data_feed.py — Point-in-time market data feed for historical simulation.

Provides strict isolation: bar queries for timestamp T return exclusively data <= T.
Supports execution price lookup for next_open and next_close conventions.
"""
from __future__ import annotations

from typing import Dict, List, Optional
import pandas as pd


class PointInTimeDataFeed:
    """
    Manages historical market bars with strict point-in-time isolation.
    Guarantees no future data is returned for any evaluation timestamp T.
    """

    def __init__(self, market_bars: Dict[str, pd.DataFrame]) -> None:
        """
        Parameters:
            market_bars: Map of symbol -> DataFrame containing historical bars
                         with columns: timestamp, open, high, low, close, volume.
        """
        self._bars: Dict[str, pd.DataFrame] = {}
        self._symbols: List[str] = sorted(market_bars.keys())

        for sym, df in market_bars.items():
            if df.empty:
                continue
            df_c = df.copy()
            df_c["timestamp"] = pd.to_datetime(df_c["timestamp"])
            # Remove duplicate timestamps and sort ascending
            df_c = df_c.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
            self._bars[sym] = df_c

    @property
    def symbols(self) -> List[str]:
        """List of universe symbols."""
        return list(self._symbols)

    def get_all_trading_dates(self) -> List[pd.Timestamp]:
        """Collect and return all unique trading session timestamps across all symbols."""
        all_ts = set()
        for df in self._bars.values():
            all_ts.update(df["timestamp"].tolist())
        return sorted(list(all_ts))

    def get_bars_up_to(self, as_of_time: pd.Timestamp) -> Dict[str, pd.DataFrame]:
        """
        Retrieve historical bars strictly <= as_of_time for all symbols.

        CRITICAL POINT-IN-TIME INVARIANT:
        No row with timestamp > as_of_time is EVER included.
        """
        result: Dict[str, pd.DataFrame] = {}
        for sym, df in self._bars.items():
            # Align timezones if necessary
            ts_series = df["timestamp"]
            if as_of_time.tzinfo is not None and ts_series.dt.tz is None:
                mask = ts_series <= as_of_time.tz_localize(None)
            elif as_of_time.tzinfo is None and ts_series.dt.tz is not None:
                mask = ts_series.dt.tz_localize(None) <= as_of_time
            else:
                mask = ts_series <= as_of_time

            hist_slice = df[mask].copy()
            if not hist_slice.empty:
                result[sym] = hist_slice
        return result

    def get_current_bar(self, symbol: str, timestamp: pd.Timestamp) -> Optional[pd.Series]:
        """Retrieve the exact bar at timestamp T for a symbol, if present."""
        df = self._bars.get(symbol)
        if df is None or df.empty:
            return None

        # Reconcile tz
        ts_series = df["timestamp"]
        if timestamp.tzinfo is not None and ts_series.dt.tz is None:
            match = df[ts_series == timestamp.tz_localize(None)]
        elif timestamp.tzinfo is None and ts_series.dt.tz is not None:
            match = df[ts_series.dt.tz_localize(None) == timestamp]
        else:
            match = df[ts_series == timestamp]

        if not match.empty:
            return match.iloc[-1]
        return None

    def get_next_bar(self, symbol: str, timestamp: pd.Timestamp) -> Optional[pd.Series]:
        """
        Retrieve the immediate next trading bar strictly > timestamp.
        Used strictly to determine future fill prices according to the execution convention.
        """
        df = self._bars.get(symbol)
        if df is None or df.empty:
            return None

        ts_series = df["timestamp"]
        if timestamp.tzinfo is not None and ts_series.dt.tz is None:
            future = df[ts_series > timestamp.tz_localize(None)]
        elif timestamp.tzinfo is None and ts_series.dt.tz is not None:
            future = df[ts_series.dt.tz_localize(None) > timestamp]
        else:
            future = df[ts_series > timestamp]

        if not future.empty:
            return future.iloc[0]
        return None
