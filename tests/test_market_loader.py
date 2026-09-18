"""
tests/test_market_loader.py — Regression tests for MarketDataLoader.

Covers:
- Incremental delta append mode
- Up-to-date detection skipping redundant downloads
- Immutability of historical raw data during incremental appends
- Multi-stock concurrent ingestion with ThreadPoolExecutor
- Rate limiting pacing
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional
import pandas as pd
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from data.corporate_actions.loader import CorporateActionsLoader
from data.corporate_actions.models import CorporateAction, CorporateActionType
from data.market.loader import MarketDataLoader
from data.market.provider import IMarketDataProvider, MockMarketDataProvider
from data.market.storage import ParquetMarketDataStorage
from data.market.validator import DataQualityValidator


class ControllableMockProvider(MockMarketDataProvider):
    """Mock provider allowing programmatic control of returned bars for incremental testing."""

    def __init__(self, data_by_symbol: Dict[str, pd.DataFrame]) -> None:
        super().__init__()
        self.data = data_by_symbol
        self.call_log: List[dict] = []

    def get_daily_bars(
        self,
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        self.call_log.append({"symbol": symbol, "start_date": start_date, "end_date": end_date})
        clean = symbol.upper().replace(".NS", "").strip()
        df = self.data.get(clean, pd.DataFrame())
        if df.empty:
            return df
        out = df.copy()
        out["timestamp"] = pd.to_datetime(out["timestamp"])
        if start_date:
            out = out[out["timestamp"].dt.date >= pd.to_datetime(start_date).date()]
        if end_date:
            out = out[out["timestamp"].dt.date <= pd.to_datetime(end_date).date()]
        return out.reset_index(drop=True)

    def get_corporate_actions(
        self,
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[CorporateAction]:
        return []


@pytest.fixture
def temp_environment():
    """Create isolated temporary directory for parquet storage and corporate actions cache."""
    temp_dir = Path(tempfile.mkdtemp(prefix="apex_loader_test_"))
    storage_dir = temp_dir / "parquet"
    actions_dir = temp_dir / "corp_actions"
    storage = ParquetMarketDataStorage(base_dir=storage_dir)
    actions_loader = CorporateActionsLoader(cache_dir=actions_dir)
    validator = DataQualityValidator()
    yield temp_dir, storage, actions_loader, validator
    shutil.rmtree(temp_dir, ignore_errors=True)


def _generate_bars(symbol: str, dates: List[str], base_price: float = 100.0) -> pd.DataFrame:
    rows = []
    for i, d in enumerate(dates):
        p = base_price + i * 2.0
        rows.append({
            "timestamp": pd.to_datetime(d, utc=True),
            "symbol": symbol,
            "open": p,
            "high": p + 5.0,
            "low": p - 2.0,
            "close": p + 1.0,
            "volume": 100000.0 + i * 5000.0,
        })
    return pd.DataFrame(rows)


def test_incremental_ingestion_appends_new_bars(temp_environment):
    temp_dir, storage, actions_loader, validator = temp_environment

    dates_batch1 = ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]
    dates_batch2 = ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05",
                    "2024-01-08", "2024-01-09", "2024-01-10"]

    # Initial batch: 5 bars
    df_full = _generate_bars("RELIANCE", dates_batch2)
    provider = ControllableMockProvider({"RELIANCE": _generate_bars("RELIANCE", dates_batch1)})
    loader = MarketDataLoader(provider=provider, storage=storage, actions_loader=actions_loader, validator=validator)

    df1, rep1 = loader.ingest_symbol("RELIANCE", incremental=False)
    assert len(df1) == 5
    assert rep1.status == "PASS"

    raw1 = storage.read("RELIANCE", is_adjusted=False)
    assert len(raw1) == 5

    # Update provider with complete 8 bars
    provider.data["RELIANCE"] = df_full

    # Run incremental ingestion
    df2, rep2 = loader.ingest_symbol("RELIANCE", incremental=True)
    assert len(df2) == 8
    assert rep2.status == "PASS"

    # Verify provider was asked for delta starting 2024-01-06
    assert len(provider.call_log) == 2
    delta_call = provider.call_log[1]
    assert delta_call["start_date"] == "2024-01-06"

    # Verify stored raw and adjusted datasets now have 8 contiguous bars
    raw2 = storage.read("RELIANCE", is_adjusted=False)
    adj2 = storage.read("RELIANCE", is_adjusted=True)
    assert len(raw2) == 8
    assert len(adj2) == 8
    assert list(raw2["timestamp"].dt.strftime("%Y-%m-%d")) == dates_batch2


def test_incremental_ingestion_already_up_to_date(temp_environment):
    temp_dir, storage, actions_loader, validator = temp_environment

    dates = ["2024-01-01", "2024-01-02", "2024-01-03"]
    df = _generate_bars("TCS", dates)
    provider = ControllableMockProvider({"TCS": df})
    loader = MarketDataLoader(provider=provider, storage=storage, actions_loader=actions_loader, validator=validator)

    # Initial ingest
    loader.ingest_symbol("TCS", incremental=False)
    assert len(provider.call_log) == 1

    # Call incremental with end_date matching latest bar
    clean_df, report = loader.ingest_symbol("TCS", end_date="2024-01-03", incremental=True)
    assert len(clean_df) == 3
    assert report.status == "PASS"
    # Redundant download was skipped (no second get_daily_bars call to provider)
    assert len(provider.call_log) == 1


def test_incremental_raw_data_immutability(temp_environment):
    temp_dir, storage, actions_loader, validator = temp_environment

    dates1 = ["2024-01-01", "2024-01-02", "2024-01-03"]
    dates2 = ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]

    provider = ControllableMockProvider({"INFY": _generate_bars("INFY", dates1)})
    loader = MarketDataLoader(provider=provider, storage=storage, actions_loader=actions_loader, validator=validator)

    loader.ingest_symbol("INFY", incremental=False)
    raw_before = storage.read("INFY", is_adjusted=False)

    # Incrementally ingest subsequent dates
    provider.data["INFY"] = _generate_bars("INFY", dates2)
    loader.ingest_symbol("INFY", incremental=True)
    raw_after = storage.read("INFY", is_adjusted=False)

    # The first 3 rows must be bit-for-bit identical
    pd.testing.assert_frame_equal(raw_before, raw_after.iloc[:3].reset_index(drop=True))


def test_concurrent_universe_ingestion(temp_environment):
    temp_dir, storage, actions_loader, validator = temp_environment

    provider = MockMarketDataProvider()
    loader = MarketDataLoader(provider=provider, storage=storage, actions_loader=actions_loader, validator=validator)

    target_symbols = ["RELIANCE", "TCS", "INFY"]
    reports = loader.ingest_benchmark_universe(
        symbols=target_symbols,
        start_date="2024-01-01",
        end_date="2024-01-10",
        max_workers=3,
        report_path=temp_dir / "quality_report.csv",
    )

    assert len(reports) == 3
    for rep in reports:
        assert rep.status == "PASS"
        assert rep.rows >= 5
    assert [r.symbol for r in reports] == target_symbols


def test_rate_limit_pacing(temp_environment):
    temp_dir, storage, actions_loader, validator = temp_environment

    provider = MockMarketDataProvider()
    loader = MarketDataLoader(provider=provider, storage=storage, actions_loader=actions_loader, validator=validator)

    target_symbols = ["RELIANCE", "TCS"]
    start_t = time.perf_counter()
    reports = loader.ingest_benchmark_universe(
        symbols=target_symbols,
        start_date="2024-01-01",
        end_date="2024-01-05",
        max_workers=1,
        rate_limit_delay=0.15,
        report_path=temp_dir / "quality_report.csv",
    )
    elapsed = time.perf_counter() - start_t

    assert len(reports) == 2
    assert elapsed >= 0.14, f"Expected pacing delay >= 0.14s, got {elapsed:.3f}s"
