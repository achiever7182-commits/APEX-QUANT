"""
data/market/loader.py — End-to-End Market Data Ingestion Pipeline and CLI for APEX QUANT.

Coordinates:
  Provider -> Raw Parquet -> Corporate Actions -> Normalization -> Quality Validation -> Processed Parquet.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple
import pandas as pd

from data.corporate_actions.adjuster import CorporateActionAdjuster
from data.corporate_actions.loader import CorporateActionsLoader
from data.corporate_actions.models import CorporateAction
from data.market.calendar import NSEMarketCalendar
from data.market.normalizer import DataNormalizer
from data.market.provider import IMarketDataProvider, MockMarketDataProvider, YahooFinanceProvider
from data.market.storage import ParquetMarketDataStorage
from data.market.validator import DataQualityReport, DataQualityValidator

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

BENCHMARK_SYMBOLS = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]


class MarketDataLoader:
    """
    Production-grade market data orchestrator for Indian equities.
    
    Guarantees:
    - Raw downloaded data is archived immutably in parquet/raw/
    - Corporate actions are detected, stored, and applied backward
    - Data is normalized and validated against the 12 data quality rules
    - Processed data is stored in parquet/adjusted/
    - Comprehensive audit reports are emitted
    """

    def __init__(
        self,
        provider: Optional[IMarketDataProvider] = None,
        storage: Optional[ParquetMarketDataStorage] = None,
        actions_loader: Optional[CorporateActionsLoader] = None,
        validator: Optional[DataQualityValidator] = None,
        adjust_splits: Optional[bool] = None,
    ) -> None:
        self.provider = provider or YahooFinanceProvider()
        self.storage = storage or ParquetMarketDataStorage()
        self.actions_loader = actions_loader or CorporateActionsLoader()
        self.validator = validator or DataQualityValidator()
        self._adjust_splits_override = adjust_splits

    def ingest_symbol(
        self,
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Tuple[pd.DataFrame, DataQualityReport]:
        """
        Ingest, adjust, validate, and store historical daily data for a single symbol.
        """
        canonical = DataNormalizer.normalize_symbol(symbol)
        logger.info(f"==> Ingesting historical data for {canonical}...")

        # 1. Fetch raw data from provider
        raw_df = self.provider.get_daily_bars(canonical, start_date=start_date, end_date=end_date)
        if raw_df.empty:
            raise ValueError(f"No historical data received from provider for symbol {canonical}.")

        # 2. Archive RAW unadjusted data (Never overwritten or modified)
        self.storage.write(raw_df, canonical, is_adjusted=False)
        logger.info(f"Saved {len(raw_df)} raw bars to parquet/raw/symbol={canonical}")

        # 3. Fetch and cache corporate actions
        actions = self.provider.get_corporate_actions(canonical, start_date=start_date, end_date=end_date)
        if actions:
            self.actions_loader.save_actions(canonical, actions)
            logger.info(f"Recorded {len(actions)} corporate action events for {canonical}.")

        # 4. Apply deterministic corporate action adjustments
        # Check provider contract: if provider bars are already split-adjusted (e.g. Yahoo Finance),
        # do not re-apply splits to prevent double adjustment.
        if self._adjust_splits_override is not None:
            should_adjust_splits = self._adjust_splits_override
        else:
            is_provider_split_adjusted = getattr(self.provider, "is_split_adjusted", False)
            should_adjust_splits = not is_provider_split_adjusted

        adjusted_df = CorporateActionAdjuster.adjust_historical_bars(
            raw_df,
            actions,
            adjust_dividends=False,
            adjust_splits=should_adjust_splits,
        )

        # 5. Normalize schema, types, and verify OHLC integrity
        clean_df, norm_logs = DataNormalizer.normalize(adjusted_df, symbol=canonical)
        for log_msg in norm_logs:
            logger.debug(log_msg)

        # 6. Validate with DataQualityValidator
        report = self.validator.validate_series(clean_df, canonical, corporate_actions_count=len(actions))

        # 7. Store processed data in partitioned parquet
        self.storage.write(clean_df, canonical, is_adjusted=True)
        logger.info(f"Saved {len(clean_df)} adjusted bars to parquet/adjusted/symbol={canonical} (Status: {report.status})")

        return clean_df, report

    def ingest_benchmark_universe(
        self,
        symbols: Optional[Sequence[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[DataQualityReport]:
        """
        Ingest the benchmark universe (RELIANCE, TCS, INFY, HDFCBANK, ICICIBANK).
        Produces summary quality audit table.
        """
        target_symbols = symbols or BENCHMARK_SYMBOLS
        reports: List[DataQualityReport] = []

        print("\n" + "=" * 78)
        print("  APEX QUANT — BENCHMARK UNIVERSE MARKET DATA INGESTION")
        print("  Universe: " + ", ".join(target_symbols))
        print("=" * 78 + "\n")

        for sym in target_symbols:
            try:
                _, rep = self.ingest_symbol(sym, start_date=start_date, end_date=end_date)
                reports.append(rep)
            except Exception as e:
                logger.error(f"Failed to ingest {sym}: {e}")
                reports.append(
                    DataQualityReport(
                        symbol=sym,
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
                        corporate_actions=0,
                        status="FAIL",
                        anomalies=[str(e)],
                    )
                )

        # Save summary report CSV
        report_path = Path("data_storage/quality_report.csv")
        self.validator.save_reports_to_csv(reports, report_path)
        print(f"\n[OK] Benchmark ingestion complete. Quality report saved to: {report_path}")
        self._print_quality_table(reports)
        return reports

    @staticmethod
    def _print_quality_table(reports: Sequence[DataQualityReport]) -> None:
        """Pretty-print tabular quality report to stdout."""
        header = f"{'Symbol':<12} | {'Rows':<6} | {'Start Date':<10} | {'End Date':<10} | {'Missing':<7} | {'Dups':<5} | {'CorpAct':<7} | {'Status':<7}"
        sep = "-" * len(header)
        print(sep)
        print(header)
        print(sep)
        for r in reports:
            print(f"{r.symbol:<12} | {r.rows:<6} | {r.start_date:<10} | {r.end_date:<10} | {r.missing_trading_days:<7} | {r.duplicates:<5} | {r.corporate_actions:<7} | {r.status:<7}")
        print(sep)


def main() -> None:
    """CLI entrypoint for data.market.loader."""
    parser = argparse.ArgumentParser(description="APEX QUANT Market Data Ingestion CLI")
    parser.add_argument("--symbol", type=str, help="Ingest a single stock (e.g. RELIANCE, TCS)")
    parser.add_argument("--benchmark", action="store_true", help="Ingest the 5 benchmark NIFTY stocks")
    parser.add_argument("--start", type=str, default=None, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default=None, help="End date (YYYY-MM-DD)")
    parser.add_argument("--mock", action="store_true", help="Use deterministic mock data provider")

    args = parser.parse_args()

    provider = MockMarketDataProvider() if args.mock else YahooFinanceProvider()
    loader = MarketDataLoader(provider=provider)

    if args.benchmark:
        loader.ingest_benchmark_universe(start_date=args.start, end_date=args.end)
    elif args.symbol:
        _, rep = loader.ingest_symbol(args.symbol, start_date=args.start, end_date=args.end)
        loader._print_quality_table([rep])
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
