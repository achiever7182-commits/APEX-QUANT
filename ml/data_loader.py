"""
ml/data_loader.py — Historical market data loader with local CSV caching.

Caches downloaded Binance OHLCV data locally so the bot does not repeatedly
fetch large datasets over the network.
"""

from __future__ import annotations

import os
from typing import Sequence
import pandas as pd

from core.strategy import MarketData
from adapters.binance_public_data_adapter import BinancePublicDataAdapter
from config import ML_HISTORICAL_DATA_DIR


def clean_symbol(symbol: str) -> str:
    """Normalize symbol to standard identifier (e.g. 'BTC/USDT' -> 'BTCUSDT')."""
    return symbol.replace("/", "").replace("-", "").upper()


def format_symbol_pair(symbol: str) -> str:
    """Ensure symbol is in 'BASE/QUOTE' format for CCXT adapter."""
    clean = clean_symbol(symbol)
    if clean.endswith("USDT"):
        base = clean[:-4]
        return f"{base}/USDT"
    return symbol


def candles_to_dataframe(candles: Sequence[MarketData]) -> pd.DataFrame:
    """Convert a sequence of MarketData objects to a clean chronological DataFrame."""
    records = [
        {
            "timestamp": c.timestamp,
            "open": float(c.open),
            "high": float(c.high),
            "low": float(c.low),
            "close": float(c.close),
            "volume": float(c.volume),
        }
        for c in candles
    ]
    df = pd.DataFrame(records)
    if not df.empty:
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df = df.sort_values("timestamp").reset_index(drop=True)
    return df


def dataframe_to_candles(df: pd.DataFrame, symbol: str = "BTC/USDT") -> list[MarketData]:
    """Convert a DataFrame back to a list of MarketData objects."""
    candles: list[MarketData] = []
    for _, row in df.iterrows():
        candles.append(
            MarketData(
                symbol=symbol,
                timestamp=int(row["timestamp"]),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
            )
        )
    return candles


def timeframe_to_minutes(tf: str) -> int:
    """Convert timeframe string to duration in minutes."""
    tf = tf.strip().lower()
    if tf.endswith("m"):
        return int(tf[:-1])
    elif tf.endswith("h"):
        return int(tf[:-1]) * 60
    elif tf.endswith("d"):
        return int(tf[:-1]) * 1440
    elif tf.endswith("w"):
        return int(tf[:-1]) * 10080
    return 60


def load_historical_data(
    symbol: str = "BTC/USDT",
    timeframe: str = "1h",
    days: int = 730,
    force_download: bool = False,
    cache_dir: str = ML_HISTORICAL_DATA_DIR,
) -> list[MarketData]:
    """
    Load historical candles for a symbol and timeframe.

    Checks local cache in `data/historical/{clean_symbol}_{timeframe}.csv` first.
    Verifies that the cache contains enough candles to cover the requested days (~90% threshold).
    If cached and adequate (and not `force_download`), loads from CSV.
    Otherwise fetches fresh historical data from Binance and updates the cache.
    """
    os.makedirs(cache_dir, exist_ok=True)
    clean = clean_symbol(symbol)
    pair = format_symbol_pair(symbol)
    csv_path = os.path.join(cache_dir, f"{clean}_{timeframe}.csv")

    tf_mins = timeframe_to_minutes(timeframe)
    expected_candles = int((days * 1440) / max(1, tf_mins))
    min_required = int(expected_candles * 0.90)

    if not force_download and os.path.exists(csv_path):
        try:
            df = pd.read_csv(csv_path)
            if len(df) >= min_required:
                print(f"[data_loader] Loaded {len(df):,} cached candles from: {csv_path} (covers {days} days)")
                return dataframe_to_candles(df, symbol=pair)
            else:
                print(
                    f"[data_loader] Cached dataset ({len(df):,} candles) is smaller than required "
                    f"for {days} days ({expected_candles:,} expected). Fetching fresh data from Binance..."
                )
        except Exception as err:
            print(f"[data_loader] Warning reading cache {csv_path}: {err}. Fetching fresh data...")

    # Fetch fresh historical candles from public Binance API
    print(f"[data_loader] Fetching {days} days of {pair} {timeframe} candles from Binance...")
    adapter = BinancePublicDataAdapter()
    candles = adapter.fetch_historical_candles(
        symbol=pair,
        timeframe=timeframe,
        since_days_ago=days,
    )

    if not candles:
        raise RuntimeError(f"No historical candles returned for {pair} {timeframe}")

    df = candles_to_dataframe(candles)
    # Persist to local cache
    try:
        df.to_csv(csv_path, index=False)
        print(f"[data_loader] Cached {len(df):,} candles to: {csv_path}")
    except Exception as err:
        print(f"[data_loader] Warning: Could not write cache to {csv_path}: {err}")

    return candles
