"""
data/realtime/bar_aggregator.py — Real-Time Streaming Candlestick Bar Aggregator.

Aggregates incoming tick quotes into discrete interval bars (1m, 5m, 15m, etc.)
with strict boundary alignment and explicit completion flags.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional
from data.market.models import MarketBar
from data.realtime.models import AggregatedBar, RealtimeQuote
from data.realtime.normalizer import SymbolNormalizer


class RealtimeBarAggregator:
    """
    Aggregates tick/quote updates into discrete OHLCV candlestick bars.
    
    Invariants:
      - Bars are strictly bounded by configured interval duration.
      - A bar is marked is_complete=True ONLY when its interval has elapsed
        and an event for a subsequent interval arrives.
      - Produces standard MarketBar representations for feature pipelines.
    """

    def __init__(
        self,
        interval_seconds: int = 300,  # default 5 minutes
        on_bar_completed: Optional[Callable[[AggregatedBar], None]] = None,
    ):
        self.interval_seconds: int = int(interval_seconds)
        self.on_bar_completed: Optional[Callable[[AggregatedBar], None]] = on_bar_completed

        self._active_bars: Dict[str, AggregatedBar] = {}
        self._completed_bars: Dict[str, List[AggregatedBar]] = {}
        self._last_cumulative_volumes: Dict[str, float] = {}

    def _align_interval_start(self, dt: datetime) -> datetime:
        """Align datetime to nearest preceding interval boundary."""
        epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
        dt_utc = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        seconds = int((dt_utc - epoch).total_seconds())
        aligned_seconds = (seconds // self.interval_seconds) * self.interval_seconds
        return epoch + timedelta(seconds=aligned_seconds)

    def process_quote(self, quote: RealtimeQuote) -> Optional[AggregatedBar]:
        """
        Ingest a quote. If it closes out a previous bar interval, returns the completed bar.
        """
        canonical = SymbolNormalizer.to_canonical(quote.symbol)
        ts = quote.timestamp if quote.timestamp.tzinfo else quote.timestamp.replace(tzinfo=timezone.utc)
        px = quote.last_price

        # Determine volume delta
        last_vol = self._last_cumulative_volumes.get(canonical)
        if last_vol is not None and quote.volume >= last_vol:
            vol_delta = quote.volume - last_vol
        else:
            vol_delta = quote.volume
        self._last_cumulative_volumes[canonical] = quote.volume

        interval_start = self._align_interval_start(ts)
        interval_end = interval_start + timedelta(seconds=self.interval_seconds)

        active = self._active_bars.get(canonical)
        completed_bar: Optional[AggregatedBar] = None

        if active is None:
            # First bar for this symbol
            self._active_bars[canonical] = AggregatedBar(
                symbol=canonical,
                start_time=interval_start,
                end_time=interval_end,
                interval_seconds=self.interval_seconds,
                open=px,
                high=px,
                low=px,
                close=px,
                volume=max(0.0, vol_delta),
                ticks_count=1,
                is_complete=False,
            )
        elif ts >= active.end_time:
            # Previous bar interval has concluded!
            active.is_complete = True
            completed_bar = active
            self._completed_bars.setdefault(canonical, []).append(completed_bar)

            if self.on_bar_completed:
                try:
                    self.on_bar_completed(completed_bar)
                except Exception:
                    pass

            # Initialize new active bar for current interval
            self._active_bars[canonical] = AggregatedBar(
                symbol=canonical,
                start_time=interval_start,
                end_time=interval_end,
                interval_seconds=self.interval_seconds,
                open=px,
                high=px,
                low=px,
                close=px,
                volume=max(0.0, vol_delta),
                ticks_count=1,
                is_complete=False,
            )
        else:
            # Tick belongs to active bar
            active.update(price=px, volume_delta=vol_delta, tick_time=ts)

        return completed_bar

    def get_active_bar(self, symbol: str) -> Optional[AggregatedBar]:
        """Return currently forming (incomplete) bar."""
        canonical = SymbolNormalizer.to_canonical(symbol)
        return self._active_bars.get(canonical)

    def get_completed_bars(self, symbol: str) -> List[AggregatedBar]:
        """Return list of historical completed bars aggregated in this session."""
        canonical = SymbolNormalizer.to_canonical(symbol)
        return list(self._completed_bars.get(canonical, []))

    def clear(self) -> None:
        """Reset aggregator state."""
        self._active_bars.clear()
        self._completed_bars.clear()
        self._last_cumulative_volumes.clear()

    @staticmethod
    def to_market_bar(bar: AggregatedBar) -> MarketBar:
        """
        Convert AggregatedBar to standard MarketBar for downstream features & ML.
        """
        norm = SymbolNormalizer.normalize(bar.symbol)
        return MarketBar(
            symbol=norm.ticker,
            exchange=norm.exchange,
            timestamp=bar.end_time,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=bar.volume,
        )
