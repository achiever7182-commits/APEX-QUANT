"""
data/market/storage.py — Scalable Apache Parquet Market Data Storage Engine for APEX QUANT.

Implements high-performance columnar storage partitioned by symbol (Hive-style),
supporting efficient range queries across hundreds of Indian equities without excessive RAM usage.
"""

from __future__ import annotations

from datetime import date, datetime
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

logger = logging.getLogger(__name__)

DEFAULT_BASE_STORAGE = Path("data_storage/parquet")


class ParquetMarketDataStorage:
    """
    Manages reading and writing partitioned Parquet datasets for APEX QUANT.
    
    Layout:
    data_storage/parquet/
      ├── raw/
      │   ├── symbol=RELIANCE/data.parquet
      │   └── symbol=TCS/data.parquet
      └── adjusted/
          ├── symbol=RELIANCE/data.parquet
          └── symbol=TCS/data.parquet
    """

    def __init__(self, base_dir: Optional[Union[str, Path]] = None) -> None:
        self.base_dir = Path(base_dir) if base_dir else DEFAULT_BASE_STORAGE
        self.raw_dir = self.base_dir / "raw"
        self.adjusted_dir = self.base_dir / "adjusted"

        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.adjusted_dir.mkdir(parents=True, exist_ok=True)

    def _get_symbol_dir(self, symbol: str, is_adjusted: bool = True) -> Path:
        clean = symbol.upper().replace(".NS", "").replace(".BO", "").strip()
        root = self.adjusted_dir if is_adjusted else self.raw_dir
        sym_dir = root / f"symbol={clean}"
        sym_dir.mkdir(parents=True, exist_ok=True)
        return sym_dir

    def _get_file_path(self, symbol: str, is_adjusted: bool = True) -> Path:
        return self._get_symbol_dir(symbol, is_adjusted) / "data.parquet"

    def write(
        self,
        df: pd.DataFrame,
        symbol: str,
        is_adjusted: bool = False,
    ) -> Path:
        """
        Write DataFrame to partitioned Parquet file.
        Overwrites existing partition cleanly.
        """
        if df.empty:
            raise ValueError(f"Cannot write empty DataFrame for symbol {symbol}")

        clean_sym = symbol.upper().replace(".NS", "").replace(".BO", "").strip()
        out = df.copy()

        # Ensure symbol column is present in written parquet schema
        if "symbol" not in out.columns:
            out["symbol"] = clean_sym

        # Ensure timestamp is datetime64
        if not pd.api.types.is_datetime64_any_dtype(out["timestamp"]):
            out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True)
        out = out.sort_values("timestamp").reset_index(drop=True)

        target_file = self._get_file_path(clean_sym, is_adjusted=is_adjusted)
        
        # Write using pyarrow table for strict schema preservation
        table = pa.Table.from_pandas(out, preserve_index=False)
        pq.write_table(table, target_file, compression="SNAPPY")
        logger.info(f"Wrote {len(out)} bars for {clean_sym} to {target_file}")
        return target_file

    def read(
        self,
        symbol: str,
        is_adjusted: bool = True,
    ) -> pd.DataFrame:
        """Read full dataset for a symbol."""
        clean_sym = symbol.upper().replace(".NS", "").replace(".BO", "").strip()
        target_file = self._get_file_path(clean_sym, is_adjusted=is_adjusted)
        if not target_file.exists():
            return pd.DataFrame()

        table = pq.read_table(target_file)
        df = table.to_pandas()
        if not df.empty:
            if "timestamp" in df.columns:
                df["timestamp"] = pd.to_datetime(df["timestamp"])
                df = df.sort_values("timestamp").reset_index(drop=True)
            if "symbol" not in df.columns:
                df["symbol"] = clean_sym
        return df

    def append(
        self,
        df: pd.DataFrame,
        symbol: str,
        is_adjusted: bool = False,
    ) -> Path:
        """Append new bars to existing dataset with automatic deduplication."""
        existing = self.read(symbol, is_adjusted=is_adjusted)
        if existing.empty:
            return self.write(df, symbol, is_adjusted=is_adjusted)

        combined = pd.concat([existing, df], ignore_index=True)
        combined["timestamp"] = pd.to_datetime(combined["timestamp"], utc=True)
        combined = combined.drop_duplicates(subset=["timestamp"], keep="last")
        combined = combined.sort_values("timestamp").reset_index(drop=True)
        return self.write(combined, symbol, is_adjusted=is_adjusted)

    def query_by_symbol(
        self,
        symbol: str,
        start_date: Optional[Union[str, date, pd.Timestamp]] = None,
        end_date: Optional[Union[str, date, pd.Timestamp]] = None,
        is_adjusted: bool = True,
    ) -> pd.DataFrame:
        """
        Query historical bars for a single symbol with date slicing.
        
        Date Convention:
        - When start_date / end_date is a calendar date (e.g. '2024-01-15' or datetime.date):
            Slices by calendar date: timestamp.date() <= end_date.
            This allows a post-market query on 2024-01-15 to include the complete daily bar
            belonging to that date, while strictly excluding any future calendar dates.
            For pre-market evaluations, callers should supply the previous trading day as end_date.
        - When an explicit intraday timestamp is provided (e.g. '2024-01-15 11:30:00'):
            Slices by precise timestamp: timestamp <= dt_end.
        """
        df = self.read(symbol, is_adjusted=is_adjusted)
        if df.empty:
            return df

        ts_tz = df["timestamp"].dt.tz

        if start_date:
            is_cal_start = False
            cal_start = None
            if isinstance(start_date, date) and not isinstance(start_date, datetime):
                is_cal_start = True
                cal_start = start_date
            elif isinstance(start_date, str) and len(start_date.strip().split("T")[0].split(" ")[0]) == len(start_date.strip()):
                is_cal_start = True
                cal_start = pd.to_datetime(start_date).date()

            if is_cal_start and cal_start is not None:
                df = df[df["timestamp"].dt.date >= cal_start]
            else:
                dt_start = pd.to_datetime(start_date)
                if ts_tz is not None and dt_start.tzinfo is None:
                    dt_start = dt_start.tz_localize(ts_tz)
                elif ts_tz is None and dt_start.tzinfo is not None:
                    dt_start = dt_start.tz_localize(None)
                df = df[df["timestamp"] >= dt_start]

        if end_date:
            is_cal_end = False
            cal_end = None
            if isinstance(end_date, date) and not isinstance(end_date, datetime):
                is_cal_end = True
                cal_end = end_date
            elif isinstance(end_date, str) and len(end_date.strip().split("T")[0].split(" ")[0]) == len(end_date.strip()):
                is_cal_end = True
                cal_end = pd.to_datetime(end_date).date()

            if is_cal_end and cal_end is not None:
                df = df[df["timestamp"].dt.date <= cal_end]
            else:
                dt_end = pd.to_datetime(end_date)
                if ts_tz is not None and dt_end.tzinfo is None:
                    dt_end = dt_end.tz_localize(ts_tz)
                elif ts_tz is None and dt_end.tzinfo is not None:
                    dt_end = dt_end.tz_localize(None)
                df = df[df["timestamp"] <= dt_end]

        return df.reset_index(drop=True)

    def query_by_date_range(
        self,
        symbols: Sequence[str],
        start_date: Union[str, pd.Timestamp],
        end_date: Union[str, pd.Timestamp],
        is_adjusted: bool = True,
    ) -> pd.DataFrame:
        """
        Query cross-sectional multi-symbol panel for a date range.
        Returns a single unified DataFrame with a 'symbol' column.
        """
        frames = []
        for s in symbols:
            clean = s.upper().replace(".NS", "").replace(".BO", "").strip()
            sdf = self.query_by_symbol(clean, start_date=start_date, end_date=end_date, is_adjusted=is_adjusted)
            if not sdf.empty:
                sdf = sdf.copy()
                if "symbol" not in sdf.columns:
                    sdf["symbol"] = clean
                frames.append(sdf)

        if not frames:
            return pd.DataFrame()
        panel = pd.concat(frames, ignore_index=True)
        panel = panel.sort_values(["timestamp", "symbol"]).reset_index(drop=True)
        return panel

    def get_storage_status(self) -> Dict[str, Any]:
        """Inspect storage directory and report total symbols, rows, and disk usage."""
        status = {
            "base_dir": str(self.base_dir),
            "raw_symbols": [],
            "adjusted_symbols": [],
            "total_files": 0,
            "total_size_bytes": 0,
            "symbol_details": {},
        }

        for path in self.base_dir.rglob("*.parquet"):
            status["total_files"] += 1
            status["total_size_bytes"] += path.stat().st_size
            parts = path.parts
            is_adj = "adjusted" in parts
            sym_part = [p for p in parts if p.startswith("symbol=")]
            if sym_part:
                sym = sym_part[0].replace("symbol=", "")
                if is_adj:
                    if sym not in status["adjusted_symbols"]:
                        status["adjusted_symbols"].append(sym)
                else:
                    if sym not in status["raw_symbols"]:
                        status["raw_symbols"].append(sym)

                if sym not in status["symbol_details"]:
                    status["symbol_details"][sym] = {"raw": False, "adjusted": False, "rows": 0}
                if is_adj:
                    status["symbol_details"][sym]["adjusted"] = True
                    # Read row count efficiently from parquet metadata
                    meta = pq.read_metadata(path)
                    status["symbol_details"][sym]["rows"] = meta.num_rows
                else:
                    status["symbol_details"][sym]["raw"] = True

        status["total_size_mb"] = round(status["total_size_bytes"] / (1024 * 1024), 2)
        return status


def main() -> None:
    """CLI entrypoint for storage status reporting."""
    import argparse
    parser = argparse.ArgumentParser(description="APEX QUANT Parquet Storage CLI")
    parser.add_argument("--status", action="store_true", help="Print storage status summary")
    args = parser.parse_args()

    storage = ParquetMarketDataStorage()
    status = storage.get_storage_status()

    print("\n" + "=" * 65)
    print("  APEX QUANT — PARQUET MARKET DATA STORAGE STATUS")
    print("=" * 65)
    print(f"Base Directory:     {status['base_dir']}")
    print(f"Total Files:        {status['total_files']}")
    print(f"Total Disk Usage:   {status['total_size_mb']} MB ({status['total_size_bytes']:,} bytes)")
    print(f"Raw Symbols:        {len(status['raw_symbols'])}: {', '.join(status['raw_symbols']) if status['raw_symbols'] else 'None'}")
    print(f"Adjusted Symbols:   {len(status['adjusted_symbols'])}: {', '.join(status['adjusted_symbols']) if status['adjusted_symbols'] else 'None'}")
    print("-" * 65)
    if status["symbol_details"]:
        print(f"{'Symbol':<12} | {'Raw File':<10} | {'Adjusted File':<14} | {'Rows':<8}")
        print("-" * 52)
        for sym, d in status["symbol_details"].items():
            print(f"{sym:<12} | {str(d['raw']):<10} | {str(d['adjusted']):<14} | {d['rows']:<8}")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    main()
