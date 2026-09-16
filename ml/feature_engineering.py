"""
ml/feature_engineering.py — Strict zero-lookahead feature extraction.

All calculations at candle t use ONLY candles <= t.
Future candles (t+1, t+2, ...) are NEVER referenced.
"""

from __future__ import annotations

import math
from typing import Sequence
import numpy as np
import pandas as pd

from core.strategy import MarketData

FEATURE_NAMES = [
    "return_1",
    "return_3",
    "return_5",
    "return_10",
    "sma_10_ratio",
    "sma_20_ratio",
    "ema_9_ratio",
    "ema_21_ratio",
    "rsi_14",
    "rsi_momentum",
    "macd_ratio",
    "macd_signal_ratio",
    "macd_diff_ratio",
    "atr_14_ratio",
    "volatility_20",
    "candle_range_pct",
    "body_to_range",
    "volume_change",
    "hour",
    "day_of_week",
]


def _calc_rsi_series(close: pd.Series, period: int = 14) -> pd.Series:
    """Calculate Relative Strength Index using Wilder's smoothing."""
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)

    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / (avg_loss + 1e-9)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi


def _calc_atr_series(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Calculate Average True Range (14-period)."""
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    return atr


def extract_features_df(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """
    Compute features on a chronological OHLCV DataFrame with ZERO lookahead bias.

    Returns:
        (df_with_features, feature_column_names) with initial NaN warmup rows dropped.
    """
    df = df.copy()
    if "datetime" not in df.columns and "timestamp" in df.columns:
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)

    close = df["close"]
    open_ = df["open"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    # 1. Returns (backward-looking)
    df["return_1"] = close.pct_change(1)
    df["return_3"] = close.pct_change(3)
    df["return_5"] = close.pct_change(5)
    df["return_10"] = close.pct_change(10)

    # 2. Moving averages
    sma_10 = close.rolling(window=10, min_periods=10).mean()
    sma_20 = close.rolling(window=20, min_periods=20).mean()
    ema_9 = close.ewm(span=9, adjust=False).mean()
    ema_21 = close.ewm(span=21, adjust=False).mean()

    df["sma_10_ratio"] = (close - sma_10) / (sma_10 + 1e-9)
    df["sma_20_ratio"] = (close - sma_20) / (sma_20 + 1e-9)
    df["ema_9_ratio"] = (close - ema_9) / (ema_9 + 1e-9)
    df["ema_21_ratio"] = (close - ema_21) / (ema_21 + 1e-9)

    # 3. Oscillators & Indicators
    df["rsi_14"] = _calc_rsi_series(close, period=14)
    df["rsi_momentum"] = df["rsi_14"].diff(3)

    ema_12 = close.ewm(span=12, adjust=False).mean()
    ema_26 = close.ewm(span=26, adjust=False).mean()
    macd = ema_12 - ema_26
    macd_signal = macd.ewm(span=9, adjust=False).mean()

    df["macd_ratio"] = macd / (close + 1e-9)
    df["macd_signal_ratio"] = macd_signal / (close + 1e-9)
    df["macd_diff_ratio"] = (macd - macd_signal) / (close + 1e-9)

    # 4. Volatility & Range
    atr_14 = _calc_atr_series(high, low, close, period=14)
    df["atr_14_ratio"] = atr_14 / (close + 1e-9)
    df["volatility_20"] = df["return_1"].rolling(window=20, min_periods=20).std()
    candle_range = (high - low)
    df["candle_range_pct"] = candle_range / (close + 1e-9)
    df["body_to_range"] = (close - open_) / (candle_range + 1e-9)

    # 5. Volume Change
    avg_vol_20 = volume.rolling(window=20, min_periods=20).mean()
    df["volume_change"] = volume / (avg_vol_20 + 1e-9)

    # 6. Time Features
    if "datetime" in df.columns:
        df["hour"] = df["datetime"].dt.hour
        df["day_of_week"] = df["datetime"].dt.dayofweek
    else:
        df["hour"] = 0
        df["day_of_week"] = 0

    return df, FEATURE_NAMES


def extract_features_single(history: Sequence[MarketData]) -> list[float] | None:
    """
    Extract feature vector for the latest candle from a historical sequence.
    Requires at least 35 candles to reliably populate lookbacks without NaN.
    """
    if len(history) < 35:
        return None

    # Use the last 50 candles for feature generation
    window = list(history[-50:])
    closes = [float(c.close) for c in window]
    opens = [float(c.open) for c in window]
    highs = [float(c.high) for c in window]
    lows = [float(c.low) for c in window]
    volumes = [float(c.volume) for c in window]

    curr_close = closes[-1]
    if curr_close <= 0:
        return None

    # 1. Returns
    ret_1 = (curr_close - closes[-2]) / closes[-2] if len(closes) >= 2 else 0.0
    ret_3 = (curr_close - closes[-4]) / closes[-4] if len(closes) >= 4 else 0.0
    ret_5 = (curr_close - closes[-6]) / closes[-6] if len(closes) >= 6 else 0.0
    ret_10 = (curr_close - closes[-11]) / closes[-11] if len(closes) >= 11 else 0.0

    # 2. SMAs & EMAs
    def ema(series: list[float], span: int) -> float:
        k = 2.0 / (span + 1)
        val = series[0]
        for x in series[1:]:
            val = x * k + val * (1.0 - k)
        return val

    sma_10 = sum(closes[-10:]) / 10.0
    sma_20 = sum(closes[-20:]) / 20.0
    ema_9 = ema(closes[-20:], 9)
    ema_21 = ema(closes[-30:], 21)

    sma_10_ratio = (curr_close - sma_10) / sma_10
    sma_20_ratio = (curr_close - sma_20) / sma_20
    ema_9_ratio = (curr_close - ema_9) / ema_9
    ema_21_ratio = (curr_close - ema_21) / ema_21

    # 3. RSI
    rsi_window = closes[-15:]
    gains, losses = [], []
    for i in range(1, len(rsi_window)):
        d = rsi_window[i] - rsi_window[i - 1]
        gains.append(d if d > 0 else 0.0)
        losses.append(-d if d < 0 else 0.0)
    avg_gain = sum(gains) / 14.0 if gains else 0.0
    avg_loss = sum(losses) / 14.0 if losses else 0.0
    rs = avg_gain / (avg_loss + 1e-9)
    rsi_14 = 100.0 - (100.0 / (1.0 + rs))

    # Past RSI (3 bars ago) for momentum
    rsi_window_past = closes[-18:-3]
    if len(rsi_window_past) == 15:
        pgains, plosses = [], []
        for i in range(1, len(rsi_window_past)):
            d = rsi_window_past[i] - rsi_window_past[i - 1]
            pgains.append(d if d > 0 else 0.0)
            plosses.append(-d if d < 0 else 0.0)
        p_avg_gain = sum(pgains) / 14.0 if pgains else 0.0
        p_avg_loss = sum(plosses) / 14.0 if plosses else 0.0
        prs = p_avg_gain / (p_avg_loss + 1e-9)
        rsi_past = 100.0 - (100.0 / (1.0 + prs))
        rsi_momentum = rsi_14 - rsi_past
    else:
        rsi_momentum = 0.0

    # 4. MACD
    ema_12 = ema(closes[-25:], 12)
    ema_26 = ema(closes[-35:], 26)
    macd = ema_12 - ema_26

    # approximate MACD signal line over recent macd values
    macd_series = []
    for offset in range(9, 0, -1):
        sub_closes = closes[: len(closes) - offset + 1]
        e12 = ema(sub_closes[-25:], 12)
        e26 = ema(sub_closes[-35:], 26)
        macd_series.append(e12 - e26)
    macd_signal = ema(macd_series, 9) if macd_series else macd

    macd_ratio = macd / curr_close
    macd_signal_ratio = macd_signal / curr_close
    macd_diff_ratio = (macd - macd_signal) / curr_close

    # 5. ATR 14
    tr_list = []
    for i in range(len(window) - 14, len(window)):
        tr1 = highs[i] - lows[i]
        tr2 = abs(highs[i] - closes[i - 1])
        tr3 = abs(lows[i] - closes[i - 1])
        tr_list.append(max(tr1, tr2, tr3))
    atr_14 = sum(tr_list) / len(tr_list) if tr_list else (highs[-1] - lows[-1])
    atr_14_ratio = atr_14 / curr_close

    # 6. Volatility (20-period return std)
    rets_20 = [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(len(closes) - 20, len(closes))]
    mean_ret = sum(rets_20) / len(rets_20) if rets_20 else 0.0
    vol_var = sum((r - mean_ret) ** 2 for r in rets_20) / max(len(rets_20) - 1, 1)
    volatility_20 = math.sqrt(vol_var)

    # 7. Range & Body
    candle_range = highs[-1] - lows[-1]
    candle_range_pct = candle_range / curr_close
    body_to_range = (curr_close - opens[-1]) / (candle_range + 1e-9)

    # 8. Volume change
    avg_vol_20 = sum(volumes[-20:]) / 20.0 if len(volumes) >= 20 else volumes[-1]
    volume_change = volumes[-1] / (avg_vol_20 + 1e-9)

    # 9. Time
    ts = window[-1].timestamp
    # Convert ms timestamp to UTC hour and day of week
    sec = ts / 1000.0
    tm = pd.to_datetime(sec, unit="s", utc=True)
    hour = tm.hour
    day_of_week = tm.dayofweek

    return [
        ret_1,
        ret_3,
        ret_5,
        ret_10,
        sma_10_ratio,
        sma_20_ratio,
        ema_9_ratio,
        ema_21_ratio,
        rsi_14,
        rsi_momentum,
        macd_ratio,
        macd_signal_ratio,
        macd_diff_ratio,
        atr_14_ratio,
        volatility_20,
        candle_range_pct,
        body_to_range,
        volume_change,
        hour,
        day_of_week,
    ]
