"""
adapters/binance_public_data_adapter.py

READ-ONLY. This adapter has no order-placing capability by design. Safe to use with no API keys.
Connects directly to Binance's live public market data endpoints via ccxt (without sandbox mode)
to fetch real historical OHLCV candles for accurate backtesting.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import ccxt
from core.strategy import MarketData


class BinancePublicDataAdapter:
    """
    Public, read-only adapter for real Binance market data.
    Structurally cannot execute trades -- contains no order-entry methods.
    """

    def __init__(self) -> None:
        self.exchange = ccxt.binance({
            "enableRateLimit": True,  # Honor Binance public endpoint rate limits
        })
        # Note: sandbox mode is intentionally False to access real historical data.
        # No API keys are supplied or needed for public market data.

    def fetch_historical_candles(
        self,
        symbol: str = "BTC/USDT",
        timeframe: str = "1h",
        since_days_ago: int = 90,
        limit_per_call: int = 1000,
    ) -> list[MarketData]:
        """
        Fetch historical candles by paginating through ccxt's fetch_ohlcv.

        Binance caps single OHLCV requests to 1000 candles. To fetch extensive
        historical periods (e.g. 90-180 days), this method calculates the starting
        timestamp and paginates forward until the current time is reached.

        Args:
            symbol: Trading pair, e.g. "BTC/USDT".
            timeframe: Candle interval, e.g. "1m", "5m", "1h", "1d".
            since_days_ago: How many days of history to retrieve.
            limit_per_call: Max candles per request (default: 1000).

        Returns:
            list[MarketData] chronologically ordered from oldest to newest.
        """
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        since_ms = now_ms - (since_days_ago * 86400 * 1000)

        all_candles_by_time: dict[int, list[Any]] = {}
        current_since = since_ms
        call_count = 0

        print(
            f"[public_data] Fetching {since_days_ago} days of REAL {symbol} {timeframe} candles from Binance..."
        )

        while current_since < now_ms:
            call_count += 1
            try:
                batch = self.exchange.fetch_ohlcv(
                    symbol,
                    timeframe=timeframe,
                    since=current_since,
                    limit=limit_per_call,
                )
            except Exception as e:
                print(f"[public_data] Warning: fetch_ohlcv error on page {call_count}: {e}")
                break

            if not batch:
                break

            new_candles = 0
            for row in batch:
                ts = int(row[0])
                if ts not in all_candles_by_time and ts <= now_ms:
                    all_candles_by_time[ts] = row
                    new_candles += 1

            last_ts = int(batch[-1][0])

            # If no new candles were added or the timestamp didn't advance, stop to avoid loops
            if new_candles == 0 or last_ts <= current_since:
                break

            current_since = last_ts + 1

            # If the batch was smaller than the limit, we've caught up to the present
            if len(batch) < limit_per_call:
                break

        sorted_rows = sorted(all_candles_by_time.values(), key=lambda r: r[0])
        print(
            f"[public_data] Collected {len(sorted_rows)} real historical candles "
            f"across {call_count} API call(s)."
        )

        return [
            MarketData(
                symbol=symbol,
                timestamp=row[0],
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=float(row[5]),
            )
            for row in sorted_rows
        ]

    def fetch_candles(
        self,
        symbol: str = "BTC/USDT",
        timeframe: str = "1m",
        limit: int = 1000,
    ) -> list[MarketData]:
        """Convenience method to fetch the most recent N candles without pagination."""
        raw = self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        return [
            MarketData(
                symbol=symbol,
                timestamp=row[0],
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=float(row[5]),
            )
            for row in raw
        ]
