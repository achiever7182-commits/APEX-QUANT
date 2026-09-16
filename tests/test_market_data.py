import os
import sys
from datetime import datetime, timezone
import pandas as pd

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from data.market.models import MarketBar, SymbolMetadata
from core.interfaces.market_data import Bar
from core.interfaces.instrument import AssetClass, Exchange


def test_market_bar_creation_valid():
    bar = MarketBar(
        symbol="RELIANCE.NS",
        exchange="NSE",
        timestamp=datetime(2024, 1, 15, 15, 30, tzinfo=timezone.utc),
        open=2500.0,
        high=2550.0,
        low=2490.0,
        close=2540.0,
        volume=1_000_000.0,
        turnover=2_540_000_000.0,
    )
    # Checks canonical symbol stripping
    assert bar.symbol == "RELIANCE"
    assert bar.exchange == "NSE"
    assert bar.is_bullish is True
    assert bar.close == 2540.0


def test_market_bar_validation_errors():
    dt = datetime(2024, 1, 15, 15, 30, tzinfo=timezone.utc)
    
    # 1. High < Low
    try:
        MarketBar(symbol="TCS", exchange="NSE", timestamp=dt, open=3000, high=2900, low=3100, close=3050, volume=100)
        assert False, "Should raise ValueError for high < low"
    except ValueError:
        pass

    # 2. Negative volume
    try:
        MarketBar(symbol="TCS", exchange="NSE", timestamp=dt, open=3000, high=3100, low=2900, close=3050, volume=-50)
        assert False, "Should raise ValueError for negative volume"
    except ValueError:
        pass

    # 3. Negative price
    try:
        MarketBar(symbol="TCS", exchange="NSE", timestamp=dt, open=-3000, high=3100, low=2900, close=3050, volume=50)
        assert False, "Should raise ValueError for negative price"
    except ValueError:
        pass


def test_market_bar_to_legacy_interface():
    bar = MarketBar(
        symbol="INFY",
        exchange="NSE",
        timestamp=datetime(2024, 1, 15, 9, 15, tzinfo=timezone.utc),
        open=1500.0,
        high=1520.0,
        low=1495.0,
        close=1510.0,
        volume=500_000.0,
    )
    legacy_bar = bar.to_bar_interface()
    assert isinstance(legacy_bar, Bar)
    assert legacy_bar.symbol == "INFY"
    assert legacy_bar.open == 1500.0
    assert legacy_bar.close == 1510.0
    assert legacy_bar.turnover == 1510.0 * 500_000.0


def test_symbol_metadata_conversion():
    meta = SymbolMetadata(
        symbol="HDFCBANK",
        name="HDFC Bank Limited",
        exchange="NSE",
        asset_class="EQUITY",
        currency="INR",
        lot_size=1,
        tick_size=0.05,
        isin="INE040A01034",
    )
    inst = meta.to_instrument()
    assert inst.symbol == "HDFCBANK"
    assert inst.exchange == Exchange.NSE
    assert inst.asset_class == AssetClass.EQUITY
    assert inst.lot_size == 1.0
    assert inst.isin == "INE040A01034"


if __name__ == "__main__":
    test_market_bar_creation_valid()
    print("  [OK] test_market_bar_creation_valid")
    test_market_bar_validation_errors()
    print("  [OK] test_market_bar_validation_errors")
    test_market_bar_to_legacy_interface()
    print("  [OK] test_market_bar_to_legacy_interface")
    test_symbol_metadata_conversion()
    print("  [OK] test_symbol_metadata_conversion")
    print("\nAll Market Data Model tests PASSED successfully.")
