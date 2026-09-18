"""
data/realtime/cache.py — Thread-Safe In-Memory Latest-Quote Cache.

Maintains current market state for all subscribed symbols with backward-overwrite
protection and staleness evaluation.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional
from data.realtime.models import RealtimeQuote
from data.realtime.normalizer import SymbolNormalizer


class LatestQuoteCache:
    """
    Thread-safe cache holding the most recent validated quote for each equity symbol.
    Guarantees that stale or out-of-order updates never overwrite newer observations.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._cache: Dict[str, RealtimeQuote] = {}

    def update(self, quote: RealtimeQuote) -> bool:
        """
        Store quote if it is newer than or equal to current cached timestamp.
        
        Returns:
            True if cache was updated, False if rejected due to timestamp regression.
        """
        canonical = SymbolNormalizer.to_canonical(quote.symbol)
        with self._lock:
            cached = self._cache.get(canonical)
            if cached is not None:
                # Ensure timestamps are comparable in UTC
                cached_ts = cached.timestamp if cached.timestamp.tzinfo else cached.timestamp.replace(tzinfo=timezone.utc)
                new_ts = quote.timestamp if quote.timestamp.tzinfo else quote.timestamp.replace(tzinfo=timezone.utc)

                if new_ts < cached_ts:
                    # Stale / regression rejection
                    return False

            self._cache[canonical] = quote
            return True

    def get_latest(self, symbol: str) -> Optional[RealtimeQuote]:
        """Retrieve most recent quote for a symbol."""
        canonical = SymbolNormalizer.to_canonical(symbol)
        with self._lock:
            return self._cache.get(canonical)

    def get_all_latest(self) -> Dict[str, RealtimeQuote]:
        """Return shallow copy of all current market quotes."""
        with self._lock:
            return dict(self._cache)

    def get_symbols(self) -> List[str]:
        """Return list of all cached symbols."""
        with self._lock:
            return list(self._cache.keys())

    def get_quote_age(self, symbol: str, as_of: Optional[datetime] = None) -> Optional[float]:
        """Calculate quote age in seconds relative to as_of or current time."""
        canonical = SymbolNormalizer.to_canonical(symbol)
        ref_t = as_of or datetime.now(timezone.utc)
        if ref_t.tzinfo is None:
            ref_t = ref_t.replace(tzinfo=timezone.utc)

        with self._lock:
            quote = self._cache.get(canonical)
            if quote is None:
                return None
            q_t = quote.timestamp if quote.timestamp.tzinfo else quote.timestamp.replace(tzinfo=timezone.utc)
            return max(0.0, (ref_t - q_t).total_seconds())

    def is_stale(
        self,
        symbol: str,
        max_staleness_seconds: float,
        as_of: Optional[datetime] = None,
    ) -> bool:
        """Check if quote for a symbol exceeds staleness threshold or is missing."""
        age = self.get_quote_age(symbol, as_of=as_of)
        if age is None:
            return True
        return age > max_staleness_seconds

    def clear(self) -> None:
        """Flush cache."""
        with self._lock:
            self._cache.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._cache)


_global_quote_cache: Optional[LatestQuoteCache] = None
_global_cache_lock = threading.Lock()


def get_global_quote_cache() -> LatestQuoteCache:
    """Return singleton instance of LatestQuoteCache."""
    global _global_quote_cache
    with _global_cache_lock:
        if _global_quote_cache is None:
            _global_quote_cache = LatestQuoteCache()
        return _global_quote_cache
