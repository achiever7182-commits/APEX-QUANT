import os
import sys
from datetime import date, datetime, timedelta
import pandas as pd

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from data.market.calendar import NSEMarketCalendar
from data.market.normalizer import DataNormalizer
from data.market.validator import DataQualityValidator


def test_normalizer_canonical_columns_and_symbols():
    raw_data = {
        "Date": ["2024-01-01", "2024-01-02"],
        "Open": [100.0, 102.0],
        "High": [105.0, 106.0],
        "Low": [98.0, 101.0],
        "Close": [103.0, 104.0],
        "Volume": [1000, 1500],
    }
    df = pd.DataFrame(raw_data)
    clean_df, logs = DataNormalizer.normalize(df, symbol="RELIANCE.NS")
    
    expected_cols = ["timestamp", "open", "high", "low", "close", "volume"]
    assert list(clean_df.columns) == expected_cols
    assert len(clean_df) == 2
    assert pd.api.types.is_datetime64_any_dtype(clean_df["timestamp"])
    assert DataNormalizer.normalize_symbol("tcs.ns") == "TCS"


def test_normalizer_rejects_corrupted_data():
    # Corrupted: high < low on row 0, negative volume on row 1, close > high on row 2
    corrupted_data = {
        "timestamp": ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"],
        "open": [100.0, 102.0, 100.0, 100.0],
        "high": [90.0, 105.0, 102.0, 105.0],    # row 0: high 90 < low 95
        "low": [95.0, 101.0, 98.0, 98.0],
        "close": [100.0, 103.0, 115.0, 102.0],  # row 2: close 115 > high 102
        "volume": [1000, -500, 1200, 1000],     # row 1: negative volume
    }
    df = pd.DataFrame(corrupted_data)
    clean_df, logs = DataNormalizer.normalize(df, symbol="INFY", drop_invalid=True)
    
    # Only row 3 should survive
    assert len(clean_df) == 1
    assert clean_df.iloc[0]["close"] == 102.0


def test_normalizer_deduplication():
    dup_data = {
        "timestamp": ["2024-01-01", "2024-01-01", "2024-01-02"],
        "open": [100.0, 101.0, 102.0],
        "high": [105.0, 106.0, 107.0],
        "low": [98.0, 99.0, 100.0],
        "close": [103.0, 104.0, 105.0],
        "volume": [1000, 2000, 1500],
    }
    df = pd.DataFrame(dup_data)
    clean_df, logs = DataNormalizer.normalize(df, symbol="HDFCBANK")
    assert len(clean_df) == 2
    # Kept latest record (close = 104.0)
    assert clean_df.iloc[0]["close"] == 104.0


def test_validator_detects_anomalies_and_calendar():
    calendar = NSEMarketCalendar()
    validator = DataQualityValidator(calendar=calendar)

    # Synthetic series skipping a Wednesday (expected trading day)
    dates = [
        "2024-01-08", # Mon
        "2024-01-09", # Tue
        # Skipping 2024-01-10 (Wed)
        "2024-01-11", # Thu
        "2024-01-12", # Fri
    ]
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(dates),
        "open": [100.0, 102.0, 104.0, 105.0],
        "high": [105.0, 106.0, 107.0, 108.0],
        "low": [98.0, 100.0, 102.0, 103.0],
        "close": [103.0, 104.0, 105.0, 106.0],
        "volume": [1000.0, 1200.0, 1100.0, 1300.0],
    })

    rep = validator.validate_series(df, symbol="ICICIBANK")
    assert rep.rows == 4
    assert rep.missing_trading_days >= 1
    assert rep.high_low_violations == 0
    assert rep.nan_rows == 0
    assert rep.status == "PASS"  # PASS because missing days are recorded as anomalies/warnings without hard failure


def test_nse_calendar_holidays_and_weekends():
    cal = NSEMarketCalendar()
    # Republic Day (Jan 26, 2024) is an official NSE holiday
    assert cal.is_trading_day(date(2024, 1, 26)) is False
    # Saturday
    assert cal.is_trading_day(date(2024, 1, 27)) is False
    # Sunday
    assert cal.is_trading_day(date(2024, 1, 28)) is False
    # Regular Monday
    assert cal.is_trading_day(date(2024, 1, 29)) is True


if __name__ == "__main__":
    test_normalizer_canonical_columns_and_symbols()
    print("  [OK] test_normalizer_canonical_columns_and_symbols")
    test_normalizer_rejects_corrupted_data()
    print("  [OK] test_normalizer_rejects_corrupted_data")
    test_normalizer_deduplication()
    print("  [OK] test_normalizer_deduplication")
    test_validator_detects_anomalies_and_calendar()
    print("  [OK] test_validator_detects_anomalies_and_calendar")
    test_nse_calendar_holidays_and_weekends()
    print("  [OK] test_nse_calendar_holidays_and_weekends")
    print("\nAll Data Normalization and Validation tests PASSED successfully.")
