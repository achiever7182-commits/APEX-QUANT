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


def test_validator_valid_adjusted_ohlcv():
    """Regression test a: Valid adjusted OHLCV data passes cleanly."""
    validator = DataQualityValidator()
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
        "open": [100.0, 102.0, 104.0],
        "high": [105.0, 106.0, 108.0],
        "low": [98.0, 100.0, 102.0],
        "close": [103.0, 104.0, 106.0],
        "volume": [1000.0, 1200.0, 1100.0],
        "adjusted_open": [50.0, 51.0, 52.0],
        "adjusted_high": [52.5, 53.0, 54.0],
        "adjusted_low": [49.0, 50.0, 51.0],
        "adjusted_close": [51.5, 52.0, 53.0],
        "adjusted_volume": [2000.0, 2400.0, 2200.0],
    })
    rep = validator.validate_series(df, symbol="RELIANCE")
    assert rep.status == "PASS"
    assert rep.nan_rows == 0
    assert rep.negative_prices == 0
    assert rep.negative_volume == 0
    assert rep.high_low_violations == 0
    assert rep.open_close_violations == 0
    assert rep.abnormal_jumps == 0
    assert len(rep.anomalies) == 0


def test_validator_invalid_adjusted_ohlc():
    """Regression test b: Violations in adjusted OHLC (high < low and close > high)."""
    validator = DataQualityValidator()
    # Row 0: adjusted_high (48.0) < adjusted_low (49.0)
    # Row 1: adjusted_close (60.0) > adjusted_high (53.0)
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(["2024-01-01", "2024-01-02"]),
        "open": [100.0, 102.0],
        "high": [105.0, 106.0],
        "low": [98.0, 100.0],
        "close": [103.0, 104.0],
        "volume": [1000.0, 1200.0],
        "adjusted_open": [50.0, 51.0],
        "adjusted_high": [48.0, 53.0],
        "adjusted_low": [49.0, 50.0],
        "adjusted_close": [48.5, 60.0],
        "adjusted_volume": [2000.0, 2400.0],
    })
    rep = validator.validate_series(df, symbol="TCS")
    assert rep.status == "FAIL"
    assert rep.high_low_violations >= 1
    assert rep.open_close_violations >= 1
    assert any("adjusted_high < adjusted_low" in a for a in rep.anomalies)
    assert any("adjusted open/close violated" in a for a in rep.anomalies)


def test_validator_negative_adjusted_volume():
    """Regression test c: Negative adjusted volume triggers anomaly and failure."""
    validator = DataQualityValidator()
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(["2024-01-01", "2024-01-02"]),
        "open": [100.0, 102.0],
        "high": [105.0, 106.0],
        "low": [98.0, 100.0],
        "close": [103.0, 104.0],
        "volume": [1000.0, 1200.0],
        "adjusted_open": [100.0, 102.0],
        "adjusted_high": [105.0, 106.0],
        "adjusted_low": [98.0, 100.0],
        "adjusted_close": [103.0, 104.0],
        "adjusted_volume": [1000.0, -500.0],
    })
    rep = validator.validate_series(df, symbol="INFY")
    assert rep.status == "FAIL"
    assert rep.negative_volume >= 1
    assert any("negative adjusted volume" in a for a in rep.anomalies)


def test_validator_abnormal_adjusted_return_jump():
    """Regression test d: Abnormal return jump in adjusted close (>20%)."""
    validator = DataQualityValidator()
    # Adjusted close jumps from 100 to 150 (+50%) while raw close has normal return (+1%)
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(["2024-01-01", "2024-01-02"]),
        "open": [100.0, 101.0],
        "high": [105.0, 106.0],
        "low": [98.0, 99.0],
        "close": [100.0, 101.0],
        "volume": [1000.0, 1200.0],
        "adjusted_open": [100.0, 150.0],
        "adjusted_high": [105.0, 155.0],
        "adjusted_low": [98.0, 145.0],
        "adjusted_close": [100.0, 150.0],
        "adjusted_volume": [1000.0, 1200.0],
    })
    rep = validator.validate_series(df, symbol="HDFCBANK", jump_threshold_pct=20.0)
    assert rep.status == "WARNING"
    assert rep.abnormal_jumps >= 1
    assert any("daily adjusted returns exceeding 20.0% threshold" in a for a in rep.anomalies)


def test_validator_absence_of_adjusted_columns_remains_valid():
    """Regression test e: Absence of adjusted columns remains valid if raw OHLCV passes."""
    validator = DataQualityValidator()
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(["2024-01-01", "2024-01-02"]),
        "open": [100.0, 102.0],
        "high": [105.0, 106.0],
        "low": [98.0, 100.0],
        "close": [103.0, 104.0],
        "volume": [1000.0, 1200.0],
    })
    rep = validator.validate_series(df, symbol="ICICIBANK")
    assert rep.status == "PASS"
    assert rep.high_low_violations == 0
    assert rep.open_close_violations == 0
    assert rep.nan_rows == 0
    assert rep.negative_prices == 0
    assert rep.negative_volume == 0
    assert rep.abnormal_jumps == 0
    assert len(rep.anomalies) == 0


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
    test_validator_valid_adjusted_ohlcv()
    print("  [OK] test_validator_valid_adjusted_ohlcv")
    test_validator_invalid_adjusted_ohlc()
    print("  [OK] test_validator_invalid_adjusted_ohlc")
    test_validator_negative_adjusted_volume()
    print("  [OK] test_validator_negative_adjusted_volume")
    test_validator_abnormal_adjusted_return_jump()
    print("  [OK] test_validator_abnormal_adjusted_return_jump")
    test_validator_absence_of_adjusted_columns_remains_valid()
    print("  [OK] test_validator_absence_of_adjusted_columns_remains_valid")
    print("\nAll Data Normalization and Validation tests PASSED successfully.")
