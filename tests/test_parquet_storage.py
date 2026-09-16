import os
import sys
import shutil
import tempfile
from pathlib import Path
import pandas as pd

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from data.market.storage import ParquetMarketDataStorage


def test_parquet_round_trip():
    temp_dir = Path(tempfile.mkdtemp(prefix="apex_test_parquet_"))
    try:
        storage = ParquetMarketDataStorage(base_dir=temp_dir)

        df = pd.DataFrame({
            "timestamp": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
            "open": [100.0, 101.0, 102.0],
            "high": [105.0, 106.0, 107.0],
            "low": [98.0, 99.0, 100.0],
            "close": [103.0, 104.0, 105.0],
            "volume": [1000.0, 1200.0, 1500.0],
            "adjusted_close": [51.5, 52.0, 52.5],
        })

        # Write to adjusted partition
        file_path = storage.write(df, "RELIANCE", is_adjusted=True)
        assert file_path.exists()
        assert "symbol=RELIANCE" in str(file_path)

        # Read back
        read_df = storage.read("RELIANCE", is_adjusted=True)
        assert len(read_df) == 3
        # Hive partition key 'symbol' is populated by pyarrow alongside all original columns
        for c in df.columns:
            assert c in read_df.columns
        assert "symbol" in read_df.columns
        assert (read_df["symbol"] == "RELIANCE").all()
        assert read_df.iloc[0]["close"] == 103.0
        assert read_df.iloc[0]["adjusted_close"] == 51.5
        assert pd.api.types.is_datetime64_any_dtype(read_df["timestamp"])
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_query_by_symbol_and_date():
    temp_dir = Path(tempfile.mkdtemp(prefix="apex_test_parquet_"))
    try:
        storage = ParquetMarketDataStorage(base_dir=temp_dir)
        df = pd.DataFrame({
            "timestamp": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"]),
            "open": [100.0, 101.0, 102.0, 103.0],
            "high": [105.0, 106.0, 107.0, 108.0],
            "low": [98.0, 99.0, 100.0, 101.0],
            "close": [103.0, 104.0, 105.0, 106.0],
            "volume": [1000.0, 1200.0, 1500.0, 1800.0],
        })
        storage.write(df, "TCS", is_adjusted=True)

        sliced = storage.query_by_symbol("TCS", start_date="2024-01-02", end_date="2024-01-03")
        assert len(sliced) == 2
        assert str(sliced.iloc[0]["timestamp"].date()) == "2024-01-02"
        assert str(sliced.iloc[1]["timestamp"].date()) == "2024-01-03"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_query_cross_sectional_panel():
    temp_dir = Path(tempfile.mkdtemp(prefix="apex_test_parquet_"))
    try:
        storage = ParquetMarketDataStorage(base_dir=temp_dir)
        dates = pd.to_datetime(["2024-01-01", "2024-01-02"])

        df_rel = pd.DataFrame({
            "timestamp": dates,
            "open": [2500.0, 2520.0], "high": [2550.0, 2560.0], "low": [2490.0, 2510.0],
            "close": [2540.0, 2550.0], "volume": [1_000_000.0, 900_000.0],
        })
        df_infy = pd.DataFrame({
            "timestamp": dates,
            "open": [1500.0, 1510.0], "high": [1530.0, 1540.0], "low": [1490.0, 1500.0],
            "close": [1520.0, 1530.0], "volume": [500_000.0, 600_000.0],
        })

        storage.write(df_rel, "RELIANCE", is_adjusted=True)
        storage.write(df_infy, "INFY", is_adjusted=True)

        panel = storage.query_by_date_range(["RELIANCE", "INFY"], start_date="2024-01-01", end_date="2024-01-02")
        assert len(panel) == 4
        assert set(panel["symbol"].unique()) == {"RELIANCE", "INFY"}
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_storage_status_inspection():
    temp_dir = Path(tempfile.mkdtemp(prefix="apex_test_parquet_"))
    try:
        storage = ParquetMarketDataStorage(base_dir=temp_dir)
        df = pd.DataFrame({
            "timestamp": pd.to_datetime(["2024-01-01", "2024-01-02"]),
            "open": [100.0, 101.0], "high": [105.0, 106.0], "low": [98.0, 99.0],
            "close": [103.0, 104.0], "volume": [1000.0, 1200.0],
        })
        storage.write(df, "HDFCBANK", is_adjusted=False)
        storage.write(df, "HDFCBANK", is_adjusted=True)

        status = storage.get_storage_status()
        assert status["total_files"] == 2
        assert "HDFCBANK" in status["raw_symbols"]
        assert "HDFCBANK" in status["adjusted_symbols"]
        assert status["symbol_details"]["HDFCBANK"]["rows"] == 2
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    test_parquet_round_trip()
    print("  [OK] test_parquet_round_trip")
    test_query_by_symbol_and_date()
    print("  [OK] test_query_by_symbol_and_date")
    test_query_cross_sectional_panel()
    print("  [OK] test_query_cross_sectional_panel")
    test_storage_status_inspection()
    print("  [OK] test_storage_status_inspection")
    print("\nAll Parquet Storage tests PASSED successfully.")
