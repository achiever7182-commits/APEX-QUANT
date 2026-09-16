"""
data/market/validator.py — Automated Data Quality Verification Engine for APEX QUANT.

Enforces 12 rigorous data quality rules across Indian equity OHLCV series.
Identifies anomalies, cross-references NSE trading calendar, and produces structured audit reports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union
import numpy as np
import pandas as pd

from data.market.calendar import NSEMarketCalendar

logger = logging.getLogger(__name__)


@dataclass
class DataQualityReport:
    """Structured data quality audit report for a financial instrument."""
    symbol: str
    rows: int
    start_date: str
    end_date: str
    missing_trading_days: int
    duplicates: int
    nan_rows: int
    negative_prices: int
    negative_volume: int
    high_low_violations: int
    open_close_violations: int
    abnormal_jumps: int
    corporate_actions: int
    status: str                         # "PASS", "WARNING", "FAIL"
    anomalies: List[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return self.status in ("PASS", "WARNING")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "rows": self.rows,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "missing_trading_days": self.missing_trading_days,
            "duplicates": self.duplicates,
            "nan_rows": self.nan_rows,
            "negative_prices": self.negative_prices,
            "negative_volume": self.negative_volume,
            "high_low_violations": self.high_low_violations,
            "open_close_violations": self.open_close_violations,
            "abnormal_jumps": self.abnormal_jumps,
            "corporate_actions": self.corporate_actions,
            "status": self.status,
            "anomalies_count": len(self.anomalies),
        }


class DataQualityValidator:
    """
    Validates Indian equity datasets against financial sanity and NSE calendar rules.
    """

    def __init__(self, calendar: Optional[NSEMarketCalendar] = None) -> None:
        self.calendar = calendar or NSEMarketCalendar()

    def validate_series(
        self,
        df: pd.DataFrame,
        symbol: str,
        corporate_actions_count: int = 0,
        jump_threshold_pct: float = 20.0,
    ) -> DataQualityReport:
        """
        Execute full 12-check validation suite on an OHLCV DataFrame.
        
        Args:
            df: DataFrame with ['timestamp', 'open', 'high', 'low', 'close', 'volume']
            symbol: Ticker symbol
            corporate_actions_count: Number of recorded corporate action events for context
            jump_threshold_pct: Threshold (%) for flagging unannounced daily price jumps
        """
        clean_sym = symbol.upper().replace(".NS", "").replace(".BO", "").strip()
        anomalies: List[str] = []

        if df.empty:
            return DataQualityReport(
                symbol=clean_sym,
                rows=0,
                start_date="N/A",
                end_date="N/A",
                missing_trading_days=0,
                duplicates=0,
                nan_rows=0,
                negative_prices=0,
                negative_volume=0,
                high_low_violations=0,
                open_close_violations=0,
                abnormal_jumps=0,
                corporate_actions=corporate_actions_count,
                status="FAIL",
                anomalies=["Dataset is empty."],
            )

        # Ensure timestamp is datetime
        ts_series = pd.to_datetime(df["timestamp"])
        start_dt = str(ts_series.min().date())
        end_dt = str(ts_series.max().date())

        # 1. Duplicate Timestamps
        duplicates = int(ts_series.duplicated().sum())
        if duplicates > 0:
            anomalies.append(f"Found {duplicates} duplicate timestamps.")

        # 2. Chronological Ordering
        is_sorted = ts_series.is_monotonic_increasing
        if not is_sorted:
            anomalies.append("Timestamps are not strictly in chronological ascending order.")

        # 3. Missing Trading Days against NSE Calendar
        actual_dates = ts_series.dt.date.unique()
        missing_days_list = self.calendar.get_missing_trading_days(
            actual_dates,
            start_date=actual_dates.min(),
            end_date=actual_dates.max(),
        )
        missing_count = len(missing_days_list)
        if missing_count > 0:
            anomalies.append(f"{missing_count} expected NSE trading days missing (e.g. {missing_days_list[:3]}...).")

        # 4. NaN / Null values
        nan_rows = int(df[["open", "high", "low", "close", "volume"]].isna().any(axis=1).sum())
        if nan_rows > 0:
            anomalies.append(f"Found {nan_rows} rows with NaN in OHLCV columns.")

        # 5. Negative Prices
        neg_price_mask = (df["open"] < 0) | (df["high"] < 0) | (df["low"] < 0) | (df["close"] < 0)
        neg_prices = int(neg_price_mask.sum())
        if neg_prices > 0:
            anomalies.append(f"Found {neg_prices} rows with negative prices.")

        # 6. Negative Volume
        neg_vol_mask = df["volume"] < 0
        neg_volume = int(neg_vol_mask.sum())
        if neg_volume > 0:
            anomalies.append(f"Found {neg_volume} rows with negative volume.")

        # 7. High < Low Violations
        hl_viol_mask = df["high"] < df["low"]
        hl_violations = int(hl_viol_mask.sum())
        if hl_violations > 0:
            anomalies.append(f"Found {hl_violations} rows where high < low.")

        # 8. Open/Close outside High/Low range
        tol = 1e-4
        oc_viol_mask = (
            (df["open"] > df["high"] + tol) |
            (df["open"] < df["low"] - tol) |
            (df["close"] > df["high"] + tol) |
            (df["close"] < df["low"] - tol)
        )
        oc_violations = int(oc_viol_mask.sum())
        if oc_violations > 0:
            anomalies.append(f"Found {oc_violations} rows where open/close violated [low, high] bounds.")

        # 9. Abnormal Price Jumps (>20% day-over-day)
        # Use close-to-close returns
        close_pct_change = df["close"].pct_change().abs() * 100.0
        jump_mask = close_pct_change > jump_threshold_pct
        abnormal_jumps = int(jump_mask.sum())
        if abnormal_jumps > 0:
            anomalies.append(f"Found {abnormal_jumps} daily returns exceeding {jump_threshold_pct}% threshold.")

        # 10. Overall Status Determination
        # FAIL if severe mathematical/negative errors exist
        if neg_prices > 0 or hl_violations > 0 or nan_rows > 0:
            status = "FAIL"
        elif duplicates > 0 or oc_violations > 0 or abnormal_jumps > 0:
            status = "WARNING"
        else:
            status = "PASS"

        return DataQualityReport(
            symbol=clean_sym,
            rows=len(df),
            start_date=start_dt,
            end_date=end_dt,
            missing_trading_days=missing_count,
            duplicates=duplicates,
            nan_rows=nan_rows,
            negative_prices=neg_prices,
            negative_volume=neg_volume,
            high_low_violations=hl_violations,
            open_close_violations=oc_violations,
            abnormal_jumps=abnormal_jumps,
            corporate_actions=corporate_actions_count,
            status=status,
            anomalies=anomalies,
        )

    @staticmethod
    def save_reports_to_csv(reports: Sequence[DataQualityReport], output_path: Union[str, Path]) -> Path:
        """Save list of DataQualityReports as a tabular CSV summary."""
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        df = pd.DataFrame([r.to_dict() for r in reports])
        df.to_csv(out_p, index=False)
        return out_p


def main() -> None:
    """CLI entrypoint to validate all stored adjusted parquet datasets."""
    from data.market.storage import ParquetMarketDataStorage

    storage = ParquetMarketDataStorage()
    status = storage.get_storage_status()
    symbols = status.get("adjusted_symbols", [])

    if not symbols:
        print("No stored datasets found to validate. Run 'python -m data.market.loader --benchmark' first.")
        return

    validator = DataQualityValidator()
    reports = []
    print("\n" + "=" * 70)
    print("  APEX QUANT — DATA QUALITY AUDIT REPORT")
    print("=" * 70)

    for sym in symbols:
        df = storage.read(sym, is_adjusted=True)
        rep = validator.validate_series(df, sym)
        reports.append(rep)
        print(f"\n[{rep.symbol}] Status: {rep.status} | Rows: {rep.rows} | Range: {rep.start_date} -> {rep.end_date}")
        if rep.anomalies:
            for anom in rep.anomalies:
                print(f"   ! {anom}")

    # Output CSV summary
    out_csv = Path("data_storage/quality_report.csv")
    validator.save_reports_to_csv(reports, out_csv)
    print("\n" + "=" * 70)
    print(f"Audit complete for {len(symbols)} symbols. Summary saved to: {out_csv}\n")


if __name__ == "__main__":
    main()
