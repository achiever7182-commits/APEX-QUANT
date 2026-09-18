"""
data/market/loader.py — End-to-End Market Data Ingestion Pipeline and CLI for APEX QUANT.

Coordinates:
  Provider -> Raw Parquet -> Corporate Actions -> Normalization -> Quality Validation -> Processed Parquet.
"""

from __future__ import annotations

import argparse
import concurrent.futures
from datetime import date, datetime, timedelta
import logging
from pathlib import Path
import sys
import time
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
    - Safe incremental ingestion appending new bars without mutating historical quotes
    - Thread-safe optional concurrency and rate-limiting pacing
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
        incremental: bool = False,
    ) -> Tuple[pd.DataFrame, DataQualityReport]:
        """
        Ingest, adjust, validate, and store historical daily data for a single symbol.

        Args:
            symbol: Ticker symbol (e.g. RELIANCE, TCS).
            start_date: Optional start date ISO string (YYYY-MM-DD).
            end_date: Optional end date ISO string (YYYY-MM-DD).
            incremental: If True and existing data is found in raw storage, fetches only missing
                         delta bars since the latest stored timestamp and appends them without
                         mutating historical raw bars.
        """
        canonical = DataNormalizer.normalize_symbol(symbol)
        logger.info(f"==> Ingesting historical data for {canonical} (incremental={incremental})...")

        raw_df: pd.DataFrame
        if incremental:
            existing_raw = self.storage.read(canonical, is_adjusted=False)
            if not existing_raw.empty and "timestamp" in existing_raw.columns:
                existing_raw = existing_raw.copy()
                existing_raw["timestamp"] = pd.to_datetime(existing_raw["timestamp"])
                latest_ts = existing_raw["timestamp"].max()
                latest_date = latest_ts.date()

                if start_date is not None:
                    req_start = pd.to_datetime(start_date).date()
                    fetch_start_d = max(req_start, latest_date + timedelta(days=1))
                else:
                    fetch_start_d = latest_date + timedelta(days=1)

                fetch_start_str = str(fetch_start_d)

                # Check if requested end_date is already covered
                already_current = False
                if end_date is not None:
                    req_end = pd.to_datetime(end_date).date()
                    if req_end <= latest_date:
                        already_current = True

                if already_current:
                    logger.info(f"{canonical} is already up-to-date through {latest_date} (requested end {end_date}). Skipping download.")
                    existing_adj = self.storage.read(canonical, is_adjusted=True)
                    if not existing_adj.empty:
                        clean_df, _ = DataNormalizer.normalize(existing_adj, symbol=canonical)
                        actions = self.actions_loader.load_actions(canonical)
                        report = self.validator.validate_series(clean_df, canonical, corporate_actions_count=len(actions))
                        return clean_df, report
                    raw_df = existing_raw
                else:
                    logger.info(f"Fetching incremental delta for {canonical} from {fetch_start_str} to {end_date or 'latest'}...")
                    try:
                        delta_df = self.provider.get_daily_bars(canonical, start_date=fetch_start_str, end_date=end_date)
                    except Exception as e:
                        logger.warning(f"Failed fetching incremental delta for {canonical}: {e}")
                        delta_df = pd.DataFrame()

                    if delta_df is not None and not delta_df.empty:
                        self.storage.append(delta_df, canonical, is_adjusted=False)
                        logger.info(f"Appended {len(delta_df)} new raw bars to parquet/raw/symbol={canonical}")
                        raw_df = self.storage.read(canonical, is_adjusted=False)
                    else:
                        logger.info(f"No new bars returned for {canonical}.")
                        raw_df = existing_raw
            else:
                # No existing data, perform initial full download
                raw_df = self.provider.get_daily_bars(canonical, start_date=start_date, end_date=end_date)
                if raw_df.empty:
                    raise ValueError(f"No historical data received from provider for symbol {canonical}.")
                self.storage.write(raw_df, canonical, is_adjusted=False)
                logger.info(f"Saved {len(raw_df)} raw bars to parquet/raw/symbol={canonical}")
        else:
            # 1. Fetch raw data from provider (full download)
            raw_df = self.provider.get_daily_bars(canonical, start_date=start_date, end_date=end_date)
            if raw_df.empty:
                raise ValueError(f"No historical data received from provider for symbol {canonical}.")

            # 2. Archive RAW unadjusted data (Never overwritten or modified)
            self.storage.write(raw_df, canonical, is_adjusted=False)
            logger.info(f"Saved {len(raw_df)} raw bars to parquet/raw/symbol={canonical}")

        # 3. Fetch and cache corporate actions
        actions = self.provider.get_corporate_actions(canonical, start_date=start_date, end_date=end_date)
        if actions:
            if incremental:
                existing_actions = self.actions_loader.load_actions(canonical)
                seen_keys = {(a.symbol, str(a.ex_date_obj), a.action_type.value) for a in existing_actions}
                combined_actions = list(existing_actions)
                for a in actions:
                    key = (a.symbol, str(a.ex_date_obj), a.action_type.value)
                    if key not in seen_keys:
                        combined_actions.append(a)
                        seen_keys.add(key)
                self.actions_loader.save_actions(canonical, combined_actions)
                actions = combined_actions
            else:
                self.actions_loader.save_actions(canonical, actions)
            logger.info(f"Recorded {len(actions)} corporate action events for {canonical}.")
        elif incremental:
            actions = self.actions_loader.load_actions(canonical)

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
        incremental: bool = False,
        max_workers: int = 1,
        rate_limit_delay: float = 0.0,
        report_path: Optional[Path] = None,
    ) -> List[DataQualityReport]:
        """
        Ingest the benchmark universe (RELIANCE, TCS, INFY, HDFCBANK, ICICIBANK).
        Produces summary quality audit table.

        Args:
            symbols: Optional list of symbols to ingest. Defaults to BENCHMARK_SYMBOLS.
            start_date: Optional start date.
            end_date: Optional end date.
            incremental: If True, fetches and appends only missing delta bars.
            max_workers: Concurrency level. If > 1, uses ThreadPoolExecutor. Defaults to 1 (synchronous).
            rate_limit_delay: Optional delay in seconds between external provider calls to avoid rate limits.
        """
        target_symbols = list(symbols or BENCHMARK_SYMBOLS)
        reports: List[DataQualityReport] = []

        print("\n" + "=" * 78)
        print("  APEX QUANT — BENCHMARK UNIVERSE MARKET DATA INGESTION")
        print(f"  Universe: {', '.join(target_symbols)}")
        print(f"  Settings: incremental={incremental}, max_workers={max_workers}, rate_limit_delay={rate_limit_delay}s")
        print("=" * 78 + "\n")

        if max_workers <= 1:
            for i, sym in enumerate(target_symbols):
                if i > 0 and rate_limit_delay > 0:
                    time.sleep(rate_limit_delay)
                try:
                    _, rep = self.ingest_symbol(
                        sym,
                        start_date=start_date,
                        end_date=end_date,
                        incremental=incremental,
                    )
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
        else:
            def _worker(item: Tuple[int, str]) -> Tuple[int, DataQualityReport]:
                idx, sym = item
                if idx > 0 and rate_limit_delay > 0:
                    time.sleep(rate_limit_delay * idx)
                try:
                    _, rep = self.ingest_symbol(
                        sym,
                        start_date=start_date,
                        end_date=end_date,
                        incremental=incremental,
                    )
                    return idx, rep
                except Exception as e:
                    logger.error(f"Failed to ingest {sym}: {e}")
                    return idx, DataQualityReport(
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

            indexed_symbols = list(enumerate(target_symbols))
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(_worker, item) for item in indexed_symbols]
                results = [f.result() for f in futures]
                results.sort(key=lambda r: r[0])
                reports = [r[1] for r in results]

        # Save summary report CSV
        target_report_path = report_path or Path("data_storage/quality_report.csv")
        self.validator.save_reports_to_csv(reports, target_report_path)
        print(f"\n[OK] Benchmark ingestion complete. Quality report saved to: {target_report_path}")
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
    parser.add_argument("--incremental", action="store_true", help="Incremental delta ingestion")
    parser.add_argument("--workers", type=int, default=1, help="Concurrent workers for universe ingestion")
    parser.add_argument("--rate-limit", type=float, default=0.0, help="Delay in seconds between provider requests")

    args = parser.parse_args()

    provider = MockMarketDataProvider() if args.mock else YahooFinanceProvider()
    loader = MarketDataLoader(provider=provider)

    if args.benchmark:
        loader.ingest_benchmark_universe(
            start_date=args.start,
            end_date=args.end,
            incremental=args.incremental,
            max_workers=args.workers,
            rate_limit_delay=args.rate_limit,
        )
    elif args.symbol:
        _, rep = loader.ingest_symbol(
            args.symbol,
            start_date=args.start,
            end_date=args.end,
            incremental=args.incremental,
        )
        loader._print_quality_table([rep])
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
