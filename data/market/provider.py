"""
data/market/provider.py — Abstract Market Data Provider and Implementations for APEX QUANT.

Supports pluggable data sources (Yahoo Finance, Broker APIs, Local Cache, Mock Data)
without coupling the storage, validation, or strategy layers to any single website.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta
import logging
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple
import numpy as np
import pandas as pd
import requests

from data.corporate_actions.models import CorporateAction, CorporateActionType

logger = logging.getLogger(__name__)


class IMarketDataProvider(ABC):
    """Abstract interface for historical market data providers."""

    @abstractmethod
    def get_daily_bars(
        self,
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Fetch daily OHLCV historical bars.
        
        Returns DataFrame with columns: ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        """
        raise NotImplementedError

    @abstractmethod
    def get_intraday_bars(
        self,
        symbol: str,
        timeframe: str = "5m",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """Fetch intraday OHLCV bars (e.g., 5m, 15m, 1h)."""
        raise NotImplementedError

    @abstractmethod
    def get_corporate_actions(
        self,
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[CorporateAction]:
        """Fetch list of historical corporate actions (splits, bonuses, dividends)."""
        raise NotImplementedError

    @abstractmethod
    def get_instruments(self) -> List[str]:
        """Return list of supported or configured instrument symbols."""
        raise NotImplementedError


class YahooFinanceProvider(IMarketDataProvider):
    """
    Production-grade HTTP market data provider using Yahoo Finance v8 chart API.
    
    Supports Indian NSE equities via standard '.NS' suffix mapping.
    Includes rate-limiting resilience, session reuse, and automatic corporate action extraction.
    """

    BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart"
    DEFAULT_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
    }

    def __init__(self, session: Optional[requests.Session] = None, timeout: int = 15) -> None:
        self.session = session or requests.Session()
        self.session.headers.update(self.DEFAULT_HEADERS)
        self.timeout = timeout

    @staticmethod
    def _to_provider_symbol(symbol: str) -> str:
        """Map canonical symbol (e.g. RELIANCE) to Yahoo Finance NSE symbol (RELIANCE.NS)."""
        clean = symbol.upper().strip()
        if clean.endswith(".NS") or clean.endswith(".BO"):
            return clean
        return f"{clean}.NS"

    @staticmethod
    def _from_provider_symbol(symbol: str) -> str:
        """Strip exchange suffix back to canonical symbol."""
        return symbol.upper().replace(".NS", "").replace(".BO", "").strip()

    def _fetch_chart_data(
        self,
        symbol: str,
        interval: str = "1d",
        range_str: str = "5y",
        period1: Optional[int] = None,
        period2: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Fetch raw JSON payload from Yahoo Finance chart endpoint with backoff."""
        provider_sym = self._to_provider_symbol(symbol)
        url = f"{self.BASE_URL}/{provider_sym}"

        params: Dict[str, Any] = {
            "interval": interval,
            "events": "div,split",
        }
        if period1 and period2:
            params["period1"] = period1
            params["period2"] = period2
        else:
            params["range"] = range_str

        max_retries = 3
        backoff = 1.0

        for attempt in range(max_retries):
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout)
                if resp.status_code == 200:
                    data = resp.json()
                    chart = data.get("chart", {})
                    if "error" in chart and chart["error"]:
                        raise ValueError(f"Yahoo API returned error: {chart['error']}")
                    results = chart.get("result")
                    if not results:
                        raise ValueError(f"No result returned for symbol {symbol}")
                    return results[0]
                elif resp.status_code == 429:
                    logger.warning(f"Rate limited by Yahoo Finance on {symbol}. Waiting {backoff}s...")
                    time.sleep(backoff)
                    backoff *= 2
                else:
                    logger.warning(f"Yahoo API returned HTTP {resp.status_code} for {symbol}.")
                    time.sleep(backoff)
            except requests.RequestException as e:
                logger.warning(f"Network error fetching {symbol} (attempt {attempt+1}/{max_retries}): {e}")
                time.sleep(backoff)
                backoff *= 2

        raise ConnectionError(f"Failed to fetch market data for {symbol} after {max_retries} attempts.")

    def get_daily_bars(
        self,
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """Fetch daily historical bars and return raw standardized DataFrame."""
        p1 = None
        p2 = None
        if start_date:
            p1 = int(datetime.fromisoformat(start_date).timestamp())
        if end_date:
            # End of specified day
            dt_end = datetime.fromisoformat(end_date) + timedelta(days=1)
            p2 = int(dt_end.timestamp())

        data = self._fetch_chart_data(symbol, interval="1d", range_str="5y", period1=p1, period2=p2)
        timestamps = data.get("timestamp", [])
        if not timestamps:
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

        quote = data.get("indicators", {}).get("quote", [{}])[0]
        opens = quote.get("open", [])
        highs = quote.get("high", [])
        lows = quote.get("low", [])
        closes = quote.get("close", [])
        volumes = quote.get("volume", [])

        records = []
        for i in range(len(timestamps)):
            # Skip records where price values are entirely null (market holidays or halted data)
            if opens[i] is None or closes[i] is None:
                continue
            records.append({
                "timestamp": pd.to_datetime(timestamps[i], unit="s", utc=True),
                "open": float(opens[i]),
                "high": float(highs[i]),
                "low": float(lows[i]),
                "close": float(closes[i]),
                "volume": float(volumes[i]) if volumes[i] is not None else 0.0,
            })

        df = pd.DataFrame(records)
        if not df.empty:
            df = df.sort_values("timestamp").reset_index(drop=True)
        return df

    def get_intraday_bars(
        self,
        symbol: str,
        timeframe: str = "5m",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """Fetch intraday historical bars (Yahoo Finance supports up to 60 days for 5m/15m)."""
        data = self._fetch_chart_data(symbol, interval=timeframe, range_str="1mo")
        timestamps = data.get("timestamp", [])
        if not timestamps:
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

        quote = data.get("indicators", {}).get("quote", [{}])[0]
        opens = quote.get("open", [])
        highs = quote.get("high", [])
        lows = quote.get("low", [])
        closes = quote.get("close", [])
        volumes = quote.get("volume", [])

        records = []
        for i in range(len(timestamps)):
            if opens[i] is None or closes[i] is None:
                continue
            records.append({
                "timestamp": pd.to_datetime(timestamps[i], unit="s", utc=True),
                "open": float(opens[i]),
                "high": float(highs[i]),
                "low": float(lows[i]),
                "close": float(closes[i]),
                "volume": float(volumes[i]) if volumes[i] is not None else 0.0,
            })

        df = pd.DataFrame(records)
        if not df.empty:
            df = df.sort_values("timestamp").reset_index(drop=True)
        return df

    def get_corporate_actions(
        self,
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[CorporateAction]:
        """Extract splits, bonus issues, and dividends from chart metadata."""
        canonical = self._from_provider_symbol(symbol)
        data = self._fetch_chart_data(symbol, interval="1d", range_str="5y")
        events = data.get("events", {})
        actions: List[CorporateAction] = []

        # Parse splits
        splits = events.get("splits", {})
        for _, s in splits.items():
            dt = datetime.fromtimestamp(s["date"]).date()
            actions.append(
                CorporateAction(
                    symbol=canonical,
                    ex_date=dt,
                    action_type=CorporateActionType.SPLIT,
                    ratio_numerator=float(s.get("numerator", 1.0)),
                    ratio_denominator=float(s.get("denominator", 1.0)),
                    details=f"Split ratio: {s.get('splitRatio', '')}",
                )
            )

        # Parse dividends
        divs = events.get("dividends", {})
        for _, d in divs.items():
            dt = datetime.fromtimestamp(d["date"]).date()
            actions.append(
                CorporateAction(
                    symbol=canonical,
                    ex_date=dt,
                    action_type=CorporateActionType.DIVIDEND,
                    value=float(d.get("amount", 0.0)),
                    details=f"Dividend: ₹{d.get('amount', 0.0)}",
                )
            )

        # Sort actions chronologically
        actions.sort(key=lambda a: a.ex_date_obj)
        return actions

    def get_instruments(self) -> List[str]:
        """Return benchmark universe."""
        return ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]


class MockMarketDataProvider(IMarketDataProvider):
    """
    Deterministic offline market data provider for unit tests and local simulation.
    
    Generates synthetic daily bars with known corporate action splits for test validation.
    """

    def __init__(self, seed: int = 42) -> None:
        self.seed = seed

    def get_daily_bars(
        self,
        symbol: str,
        start_date: Optional[str] = "2024-01-01",
        end_date: Optional[str] = "2024-03-31",
    ) -> pd.DataFrame:
        clean = symbol.upper().replace(".NS", "").strip()
        rng = np.random.default_rng(self.seed + hash(clean) % 1000)

        dt_start = pd.to_datetime(start_date or "2024-01-01")
        dt_end = pd.to_datetime(end_date or "2024-03-31")
        dates = pd.date_range(dt_start, dt_end, freq="B")  # Business days

        n = len(dates)
        base_price = 1000.0 if clean == "INFY" else 2500.0
        returns = rng.normal(loc=0.0005, scale=0.015, size=n)
        prices = base_price * np.cumprod(1 + returns)

        records = []
        for i, dt in enumerate(dates):
            close = float(prices[i])
            spread = close * 0.008
            high = close + abs(float(rng.normal(spread, spread * 0.2)))
            low = close - abs(float(rng.normal(spread, spread * 0.2)))
            open_p = float(rng.uniform(low, high))
            vol = float(rng.integers(100_000, 2_000_000))

            records.append({
                "timestamp": dt,
                "open": round(open_p, 2),
                "high": round(high, 2),
                "low": round(low, 2),
                "close": round(close, 2),
                "volume": vol,
            })

        return pd.DataFrame(records)

    def get_intraday_bars(
        self,
        symbol: str,
        timeframe: str = "5m",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        df = self.get_daily_bars(symbol, start_date, end_date)
        return df

    def get_corporate_actions(
        self,
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[CorporateAction]:
        clean = symbol.upper().replace(".NS", "").strip()
        # Return a synthetic 2:1 split on 2024-02-15 for testing
        return [
            CorporateAction(
                symbol=clean,
                ex_date="2024-02-15",
                action_type=CorporateActionType.SPLIT,
                ratio_numerator=2.0,
                ratio_denominator=1.0,
                details="Synthetic 2:1 stock split",
            )
        ]

    def get_instruments(self) -> List[str]:
        return ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]
