"""
Historical to Real-Time Market Data Handoff and Buffer Management.

Maintains rolling historical bar buffers for feature warm-up (e.g. 200 bars)
and merges them cleanly with completed real-time aggregated bars.
Ensures zero timestamp look-ahead and strict boundary de-duplication.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, List, Optional, Union
import pandas as pd

from data.market.models import MarketBar
from data.realtime.models import AggregatedBar
from data.realtime.normalizer import SymbolNormalizer

logger = logging.getLogger("apex_quant.data.realtime.handoff")


class HistoricalRealtimeHandoff:
    """
    Manages rolling historical bar buffers and appends completed real-time bars.

    Guarantees:
    1. Zero lookahead: real-time bars must have timestamps strictly >= latest historical bar.
    2. Boundary deduplication: bars with identical timestamps replace or are skipped safely.
    3. Chronological sorting: output DataFrame is always strictly ascending by timestamp.
    4. Bounded memory: keeps at most `max_buffer_size` bars per symbol (default 500).
    """

    def __init__(self, max_buffer_size: int = 500):
        self.max_buffer_size = max_buffer_size
        # Dictionary of symbol -> list of dicts with OHLCV data
        self._buffers: Dict[str, List[dict]] = {}

    def seed_history(
        self,
        symbol: str,
        bars: Union[pd.DataFrame, List[MarketBar], List[AggregatedBar]],
    ) -> int:
        """
        Seed historical bars for a symbol from Parquet/DataFrame or bar list.

        Parameters:
            symbol: Ticker symbol (e.g. 'RELIANCE' or 'NSE:RELIANCE').
            bars: Historical bars as a DataFrame or list of MarketBar/AggregatedBar.

        Returns:
            Number of bars successfully loaded into the buffer.
        """
        canonical = SymbolNormalizer.to_canonical(symbol)
        norm = SymbolNormalizer.normalize(symbol)
        records: List[dict] = []

        if isinstance(bars, pd.DataFrame):
            if bars.empty:
                self._buffers[canonical] = []
                return 0
            df = bars.copy()
            if "timestamp" not in df.columns:
                raise ValueError("DataFrame must contain 'timestamp' column.")
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df = df.sort_values("timestamp").reset_index(drop=True)

            for _, row in df.iterrows():
                records.append({
                    "symbol": norm.ticker,
                    "canonical_symbol": canonical,
                    "timestamp": row["timestamp"].to_pydatetime() if hasattr(row["timestamp"], "to_pydatetime") else row["timestamp"],
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row["volume"]),
                })
        elif isinstance(bars, list):
            for b in bars:
                if isinstance(b, MarketBar):
                    records.append({
                        "symbol": norm.ticker,
                        "canonical_symbol": canonical,
                        "timestamp": b.timestamp,
                        "open": float(b.open),
                        "high": float(b.high),
                        "low": float(b.low),
                        "close": float(b.close),
                        "volume": float(b.volume),
                    })
                elif isinstance(b, AggregatedBar):
                    records.append({
                        "symbol": norm.ticker,
                        "canonical_symbol": canonical,
                        "timestamp": b.end_time,
                        "open": float(b.open),
                        "high": float(b.high),
                        "low": float(b.low),
                        "close": float(b.close),
                        "volume": float(b.volume),
                    })
                elif isinstance(b, dict):
                    records.append({
                        "symbol": norm.ticker,
                        "canonical_symbol": canonical,
                        "timestamp": pd.to_datetime(b["timestamp"]).to_pydatetime(),
                        "open": float(b["open"]),
                        "high": float(b["high"]),
                        "low": float(b["low"]),
                        "close": float(b["close"]),
                        "volume": float(b["volume"]),
                    })
                else:
                    raise TypeError(f"Unsupported bar item type: {type(b)}")

        # Deduplicate by timestamp preserving order
        dedup_records: Dict[datetime, dict] = {}
        for r in records:
            dedup_records[r["timestamp"]] = r

        sorted_records = sorted(dedup_records.values(), key=lambda x: x["timestamp"])
        if len(sorted_records) > self.max_buffer_size:
            sorted_records = sorted_records[-self.max_buffer_size:]

        self._buffers[canonical] = sorted_records
        logger.info(
            f"Seeded {len(sorted_records)} historical bars for {canonical} "
            f"(range: {sorted_records[0]['timestamp'] if sorted_records else 'N/A'} "
            f"to {sorted_records[-1]['timestamp'] if sorted_records else 'N/A'})"
        )
        return len(sorted_records)

    def append_realtime_bar(
        self,
        symbol: str,
        bar: Union[AggregatedBar, MarketBar],
    ) -> bool:
        """
        Append a single completed real-time bar to the buffer.
        Only completed bars are appended.
        """
        if isinstance(bar, AggregatedBar) and not bar.is_complete:
            logger.warning(f"Rejecting incomplete bar for {symbol} at {bar.start_time}")
            return False

        canonical = SymbolNormalizer.to_canonical(symbol)
        norm = SymbolNormalizer.normalize(symbol)

        if canonical not in self._buffers:
            self._buffers[canonical] = []

        buf = self._buffers[canonical]

        if isinstance(bar, AggregatedBar):
            ts = bar.end_time
            o, h, l, c, v = bar.open, bar.high, bar.low, bar.close, bar.volume
        else:
            ts = bar.timestamp
            o, h, l, c, v = bar.open, bar.high, bar.low, bar.close, bar.volume

        # Enforce timestamp sanity against the last bar in the buffer
        if buf:
            last_ts = buf[-1]["timestamp"]
            if ts < last_ts:
                logger.error(
                    f"Out-of-order bar rejected for {canonical}: new bar ts {ts} < last ts {last_ts}"
                )
                return False
            if ts == last_ts:
                # Boundary collision: overwrite or replace the existing bar safely
                logger.info(f"Boundary bar timestamp match for {canonical} at {ts}. Updating bar.")
                buf[-1] = {
                    "symbol": norm.ticker,
                    "canonical_symbol": canonical,
                    "timestamp": ts,
                    "open": float(o),
                    "high": float(h),
                    "low": float(l),
                    "close": float(c),
                    "volume": float(v),
                }
                return True

        buf.append({
            "symbol": norm.ticker,
            "canonical_symbol": canonical,
            "timestamp": ts,
            "open": float(o),
            "high": float(h),
            "low": float(l),
            "close": float(c),
            "volume": float(v),
        })

        if len(buf) > self.max_buffer_size:
            self._buffers[canonical] = buf[-self.max_buffer_size:]

        return True

    def get_combined_dataframe(
        self,
        symbol: str,
        max_bars: Optional[int] = None,
    ) -> pd.DataFrame:
        """
        Get the consolidated historical + real-time bars as a pandas DataFrame.
        """
        canonical = SymbolNormalizer.to_canonical(symbol)
        buf = self._buffers.get(canonical, [])
        if not buf:
            return pd.DataFrame(columns=["symbol", "timestamp", "open", "high", "low", "close", "volume"])

        slice_data = buf[-max_bars:] if max_bars and max_bars > 0 else buf
        df = pd.DataFrame(slice_data)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.sort_values("timestamp").reset_index(drop=True)
        return df

    def get_feature_ready_dataframe(
        self,
        symbol: str,
        min_required_bars: int = 200,
    ) -> pd.DataFrame:
        """
        Returns DataFrame validated for FeatureEngine consumption.
        Verifies minimum required bars for indicator warm-up.
        """
        df = self.get_combined_dataframe(symbol)
        if len(df) < min_required_bars:
            logger.warning(
                f"Buffer for {symbol} has {len(df)} bars, which is less than "
                f"minimum required {min_required_bars} for feature warm-up."
            )
        return df

    def get_bar_count(self, symbol: str) -> int:
        """Return number of bars currently buffered for symbol."""
        canonical = SymbolNormalizer.to_canonical(symbol)
        return len(self._buffers.get(canonical, []))

    def get_latest_timestamp(self, symbol: str) -> Optional[datetime]:
        """Return latest bar timestamp for symbol, or None if buffer is empty."""
        canonical = SymbolNormalizer.to_canonical(symbol)
        buf = self._buffers.get(canonical, [])
        return buf[-1]["timestamp"] if buf else None

    def clear(self, symbol: Optional[str] = None) -> None:
        """Clear buffer for a specific symbol or all symbols."""
        if symbol:
            canonical = SymbolNormalizer.to_canonical(symbol)
            self._buffers.pop(canonical, None)
        else:
            self._buffers.clear()
