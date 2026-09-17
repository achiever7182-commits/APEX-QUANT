"""
tests/test_universe.py — Comprehensive Unit Tests for APEX QUANT Universe Subsystem.

Verifies:
  1. Domain models and Stock to Instrument conversions
  2. Point-in-time universe reconstruction on historical boundary dates
  3. Liquidity and median daily turnover calculations
  4. Composable stock filters and explicit rejection reasons
  5. Survivorship bias detection and status reporting
  6. Sector classification integrity
  7. UniverseManager end-to-end execution
"""

import os
import sys
from datetime import date, datetime
import pandas as pd

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from universe.models import (
    EligibilityResult,
    ListingStatus,
    PointInTimeStatus,
    Stock,
    UniverseMembership,
    UniverseSnapshot,
)
from universe.sector import SectorCategory, SectorInfo
from universe.constituents import CuratedNifty500Provider
from universe.nifty500 import Nifty500
from universe.liquidity import LiquidityEngine, LiquidityMetrics
from universe.stock_filter import (
    DataQualityFilter,
    HistoryFilter,
    LiquidityFilter,
    ListingStatusFilter,
    PriceFilter,
    SectorFilter,
    StockFilterPipeline,
)
from universe.universe_manager import UniverseManager


def test_stock_model_creation():
    stock = Stock(
        symbol="reliance.ns",
        company_name="Reliance Industries Limited",
        exchange="NSE",
        isin="INE002A01018",
        sector=SectorCategory.ENERGY.value,
        industry="Oil & Gas Refineries",
        listing_status=ListingStatus.ACTIVE,
    )
    assert stock.symbol == "RELIANCE"
    assert stock.is_tradable is True
    inst = stock.to_instrument()
    assert inst.symbol == "RELIANCE"
    assert inst.isin == "INE002A01018"
    assert inst.lot_size == 1.0


def test_point_in_time_membership():
    """
    Test historical membership boundary logic:
    - JIOFIN: added 2023-08-21
    - HDFCLTD: removed 2023-07-13
    - YESBANK: removed 2020-03-27
    """
    nifty = Nifty500(CuratedNifty500Provider())

    # Date 1: 2023-01-15 (Before HDFCLTD merger, before JIOFIN spin-off)
    snap_2023 = nifty.get_point_in_time_constituents(date(2023, 1, 15))
    symbols_2023 = set(snap_2023.symbols)
    assert "HDFCLTD" in symbols_2023, "HDFCLTD should be in universe on Jan 2023"
    assert "JIOFIN" not in symbols_2023, "JIOFIN should NOT be in universe before Aug 2023"

    # Date 2: 2024-01-15 (After HDFCLTD merger, after JIOFIN spin-off)
    snap_2024 = nifty.get_point_in_time_constituents(date(2024, 1, 15))
    symbols_2024 = set(snap_2024.symbols)
    assert "HDFCLTD" not in symbols_2024, "HDFCLTD should NOT be in universe in 2024"
    assert "JIOFIN" in symbols_2024, "JIOFIN should be in universe in 2024"

    # Date 3: 2020-02-01 (Before YESBANK reconstitution)
    snap_2020_early = nifty.get_point_in_time_constituents(date(2020, 2, 1))
    assert "YESBANK" in snap_2020_early.symbols

    # Date 4: 2020-04-01 (After YESBANK reconstitution)
    snap_2020_late = nifty.get_point_in_time_constituents(date(2020, 4, 1))
    assert "YESBANK" not in snap_2020_late.symbols


def test_liquidity_calculations():
    # 20 bars with price 100 and volume 100,000 -> turnover = 10,000,000
    dates = pd.date_range("2024-01-01", periods=20, freq="B")
    df = pd.DataFrame({
        "timestamp": dates,
        "close": [100.0] * 20,
        "volume": [100_000.0] * 20,
    })

    metrics = LiquidityEngine.calculate_metrics("TESTSTOCK", df, lookback_bars=20)
    assert metrics.symbol == "TESTSTOCK"
    assert metrics.median_turnover == 10_000_000.0
    assert metrics.mean_turnover == 10_000_000.0
    assert metrics.median_volume == 100_000.0
    assert metrics.valid_sessions == 20
    assert metrics.missing_percentage == 0.0
    assert metrics.last_close == 100.0


def test_stock_filters_independent():
    stock_active = Stock("INFY", "Infosys Ltd", sector="Information Technology")
    stock_delisted = Stock("OLDCO", "Old Company", listing_status=ListingStatus.DELISTED, delisting_date=date(2023, 1, 1))

    # 1. ListingStatusFilter
    flt_status = ListingStatusFilter()
    passed, reason, _ = flt_status.evaluate(stock_active, None, date(2024, 1, 1))
    assert passed is True
    passed, reason, _ = flt_status.evaluate(stock_delisted, None, date(2024, 1, 1))
    assert passed is False
    assert reason == "stock_delisted"

    # 2. PriceFilter
    flt_price = PriceFilter(min_price=10.0)
    df_penny = pd.DataFrame({"close": [5.0]})
    df_regular = pd.DataFrame({"close": [2500.0]})
    passed, reason, _ = flt_price.evaluate(stock_active, df_penny, date(2024, 1, 1))
    assert passed is False
    assert reason == "price_below_minimum"
    passed, reason, _ = flt_price.evaluate(stock_active, df_regular, date(2024, 1, 1))
    assert passed is True

    # 3. LiquidityFilter (min turnover 50 Cr / ₹50,000,000)
    flt_liq = LiquidityFilter(min_median_turnover=50_000_000.0, lookback_bars=5)
    df_illiquid = pd.DataFrame({"close": [100.0] * 5, "volume": [10_000.0] * 5})  # turnover 10 Lakhs
    passed, reason, _ = flt_liq.evaluate(stock_active, df_illiquid, date(2024, 1, 1))
    assert passed is False
    assert reason == "median_turnover_below_threshold"

    # 4. HistoryFilter (min 60 bars)
    flt_hist = HistoryFilter(min_history_bars=60)
    df_short = pd.DataFrame({"close": [100.0] * 30})
    df_long = pd.DataFrame({"close": [100.0] * 70})
    passed, reason, _ = flt_hist.evaluate(stock_active, df_short, date(2024, 1, 1))
    assert passed is False
    assert reason == "insufficient_history"
    passed, reason, _ = flt_hist.evaluate(stock_active, df_long, date(2024, 1, 1))
    assert passed is True


def test_rejection_reasons_in_pipeline():
    """Test that a stock failing multiple criteria collects all exact rejection reasons."""
    pipeline = StockFilterPipeline([
        ListingStatusFilter(),
        PriceFilter(min_price=20.0),
        HistoryFilter(min_history_bars=50),
    ])

    stock = Stock("PENNY", "Penny Stock Ltd", listing_status=ListingStatus.ACTIVE)
    # Price is 5.0 (fails PriceFilter) and only 10 bars (fails HistoryFilter)
    df = pd.DataFrame({"close": [5.0] * 10, "volume": [1000.0] * 10})

    res = pipeline.evaluate_stock(stock, df, date(2024, 1, 1))
    assert res.is_eligible is False
    assert "price_below_minimum" in res.rejection_reasons
    assert "insufficient_history" in res.rejection_reasons
    assert len(res.rejection_reasons) == 2


def test_survivorship_bias_protection():
    manager = UniverseManager()
    assert manager.point_in_time_status == PointInTimeStatus.POINT_IN_TIME_SAMPLE
    snap = manager.get_universe("2024-01-15")
    assert snap.point_in_time_status == PointInTimeStatus.POINT_IN_TIME_SAMPLE


def test_snapshot_naming_and_metadata():
    manager = UniverseManager()
    snap = manager.get_universe("2024-01-15")
    assert snap.universe_name == "NIFTY500_CURATED_SAMPLE"
    assert snap.catalog_size == 52
    assert snap.intended_universe_size == 500
    assert snap.metadata.get("is_curated_sample") is True


def test_sector_classification():
    info = SectorInfo.from_string("Information Technology")
    assert info.sector == SectorCategory.INFORMATION_TECHNOLOGY
    info_bank = SectorInfo.from_string("Private Banking")
    assert info_bank.sector == SectorCategory.FINANCIAL_SERVICES

    # Sector Filter
    sec_filter = SectorFilter(allowed_sectors={"Information Technology", "Energy"})
    stock_it = Stock("TCS", "TCS", sector="Information Technology")
    stock_auto = Stock("MARUTI", "Maruti", sector="Automobile")

    passed_it, _, _ = sec_filter.evaluate(stock_it, None, date(2024, 1, 1))
    assert passed_it is True

    passed_auto, reason, _ = sec_filter.evaluate(stock_auto, None, date(2024, 1, 1))
    assert passed_auto is False
    assert reason == "sector_not_allowed"


def test_universe_manager_end_to_end():
    manager = UniverseManager()
    snap = manager.get_universe("2024-01-15")
    assert snap.count >= 40
    assert "RELIANCE" in snap.symbols
    assert "TCS" in snap.symbols
    assert "INFY" in snap.symbols
    assert "HDFCBANK" in snap.symbols
    assert "ICICIBANK" in snap.symbols


def test_get_tradable_instruments_historical_as_of_date():
    """Verify that get_tradable_instruments evaluates historical date without date.today leakage."""
    manager = UniverseManager()
    
    # 2023-01-15: JIOFIN was not yet listed/spun off; HDFCLTD was active
    insts_2023 = manager.get_tradable_instruments(as_of_date="2023-01-15")
    symbols_2023 = {i.symbol for i in insts_2023}
    
    assert "JIOFIN" not in symbols_2023, "JIOFIN must NOT leak into 2023 historical trading universe"


def test_get_eligible_universe_end_to_end_with_parquet():
    """Verify get_eligible_universe screens stocks against real Step 2 Parquet storage."""
    manager = UniverseManager()
    eligible, results = manager.get_eligible_universe("2024-01-15")
    
    eligible_syms = {s.symbol for s in eligible}
    # Step 2 ingested benchmark stocks with complete data should be eligible
    assert "RELIANCE" in eligible_syms
    assert "TCS" in eligible_syms
    assert "INFY" in eligible_syms
    assert "HDFCBANK" in eligible_syms
    assert "ICICIBANK" in eligible_syms

    # Non-downloaded stocks should be rejected with diagnostic reason
    rejected_results = [r for r in results if not r.is_eligible]
    assert len(rejected_results) > 0
    assert any("no_price_data" in r.rejection_reasons for r in rejected_results)


if __name__ == "__main__":
    test_stock_model_creation()
    print("  [OK] test_stock_model_creation")
    test_point_in_time_membership()
    print("  [OK] test_point_in_time_membership")
    test_liquidity_calculations()
    print("  [OK] test_liquidity_calculations")
    test_stock_filters_independent()
    print("  [OK] test_stock_filters_independent")
    test_rejection_reasons_in_pipeline()
    print("  [OK] test_rejection_reasons_in_pipeline")
    test_survivorship_bias_protection()
    print("  [OK] test_survivorship_bias_protection")
    test_snapshot_naming_and_metadata()
    print("  [OK] test_snapshot_naming_and_metadata")
    test_sector_classification()
    print("  [OK] test_sector_classification")
    test_universe_manager_end_to_end()
    print("  [OK] test_universe_manager_end_to_end")
    test_get_tradable_instruments_historical_as_of_date()
    print("  [OK] test_get_tradable_instruments_historical_as_of_date")
    test_get_eligible_universe_end_to_end_with_parquet()
    print("  [OK] test_get_eligible_universe_end_to_end_with_parquet")
    print("\nAll Universe Management tests PASSED successfully.")
