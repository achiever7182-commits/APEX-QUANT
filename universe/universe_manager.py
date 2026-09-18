"""
universe/universe_manager.py — Point-in-Time Universe Manager and Inspection CLI for APEX QUANT.

Implements core.interfaces.universe.IUniverseManager, providing point-in-time constituent
reconstruction, market-data filtering, survivorship-bias verification, and CLI diagnostics.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime
import logging
from typing import Dict, List, Optional, Sequence, Tuple, Union
import pandas as pd

from core.interfaces.instrument import Instrument
from core.interfaces.universe import IUniverseManager, UniverseFilter
from data.market.storage import ParquetMarketDataStorage
from universe.constituents import CuratedNifty500Provider, IConstituentsProvider
from universe.models import EligibilityResult, PointInTimeStatus, Stock, UniverseSnapshot
from universe.nifty500 import Nifty500
from universe.stock_filter import (
    DataQualityFilter,
    HistoryFilter,
    IFilter,
    LiquidityFilter,
    ListingStatusFilter,
    PriceFilter,
    SectorFilter,
    StockFilterPipeline,
)

logger = logging.getLogger(__name__)


class UniverseManager(IUniverseManager):
    """
    Point-in-Time Universe Manager for Indian Equities.
    
    Guarantees:
    - Queries historical universe membership on the requested date (no current list leak).
    - Checks market data strictly up to the evaluation date (no lookahead bias).
    - Emits clear diagnostic rejection reasons for every screened equity.
    - Exposes point-in-time completeness status.
    """

    def __init__(
        self,
        nifty500: Optional[Nifty500] = None,
        storage: Optional[ParquetMarketDataStorage] = None,
    ) -> None:
        self.nifty500 = nifty500 or Nifty500()
        self.storage = storage or ParquetMarketDataStorage()

    @property
    def point_in_time_status(self) -> PointInTimeStatus:
        """Returns POINT_IN_TIME_COMPLETE or POINT_IN_TIME_INCOMPLETE."""
        return self.nifty500.point_in_time_status

    def get_all_symbols(self) -> List[str]:
        """
        Return all distinct symbols registered in the universe repository across all time.
        
        Guarantees that historical constituents (e.g. HDFCLTD, DHFL, YESBANK)
        are included, preventing survivorship bias during symbol discovery.
        """
        return self.nifty500.get_all_symbols()

    def get_universe(self, as_of_date: Union[date, datetime, str]) -> UniverseSnapshot:
        """
        Reconstruct the universe snapshot strictly on as_of_date.
        """
        return self.nifty500.get_point_in_time_constituents(as_of_date)

    def get_eligible_universe(
        self,
        as_of_date: Union[date, datetime, str],
        storage: Optional[ParquetMarketDataStorage] = None,
        pipeline: Optional[StockFilterPipeline] = None,
    ) -> Tuple[List[Stock], List[EligibilityResult]]:
        """
        Evaluate universe constituents on as_of_date and return eligible equities.
        
        Args:
            as_of_date: Historical evaluation date
            storage: Parquet storage engine to query historical bars
            pipeline: Configured filter chain
            
        Returns:
            Tuple of (eligible_stocks, all_eligibility_results)
        """
        store = storage or self.storage
        filter_pipe = pipeline or StockFilterPipeline()

        snapshot = self.get_universe(as_of_date)
        eval_d = snapshot.as_of_date

        eligible_stocks: List[Stock] = []
        results: List[EligibilityResult] = []

        for stock in snapshot.constituents:
            # Query market data strictly up to as_of_date (Zero Lookahead!)
            data_df = store.query_by_symbol(
                stock.symbol,
                end_date=eval_d,
                is_adjusted=True,
            )

            res = filter_pipe.evaluate_stock(stock, data_df, eval_d)
            results.append(res)

            if res.is_eligible:
                eligible_stocks.append(stock)

        return eligible_stocks, results

    def get_tradable_instruments(
        self,
        filter_criteria: Optional[UniverseFilter] = None,
        as_of_date: Optional[Union[date, str]] = None,
    ) -> List[Instrument]:
        """
        Implementation of Step 1 IUniverseManager abstract interface.
        Evaluates tradable instruments against criteria as of as_of_date.
        If as_of_date is None, defaults to date.today().
        """
        pipeline_filters: List[IFilter] = [ListingStatusFilter()]

        if filter_criteria:
            if filter_criteria.min_price:
                pipeline_filters.append(PriceFilter(min_price=filter_criteria.min_price, max_price=filter_criteria.max_price))
            if filter_criteria.min_median_turnover_20d:
                pipeline_filters.append(LiquidityFilter(min_median_turnover=filter_criteria.min_median_turnover_20d))
            if filter_criteria.allowed_sectors:
                pipeline_filters.append(SectorFilter(allowed_sectors=filter_criteria.allowed_sectors))

        pipeline = StockFilterPipeline(pipeline_filters)
        target_date = as_of_date if as_of_date is not None else date.today()
        eligible_stocks, _ = self.get_eligible_universe(target_date, pipeline=pipeline)
        return [s.to_instrument(as_of_date=target_date) for s in eligible_stocks]

    def update_constituents(self) -> None:
        """Refresh universe data (re-initializes constituent repository)."""
        self.nifty500 = Nifty500()


def main() -> None:
    """CLI entrypoint for universe inspection."""
    parser = argparse.ArgumentParser(description="APEX QUANT Universe Manager CLI")
    parser.add_argument("--date", type=str, default=str(date.today()), help="Evaluation date (YYYY-MM-DD)")
    parser.add_argument("--min-price", type=float, default=10.0, help="Minimum stock price in INR")
    parser.add_argument("--min-turnover", type=float, default=50_000_000.0, help="Minimum 20-day median turnover in INR")

    args = parser.parse_args()

    manager = UniverseManager()
    pipeline = StockFilterPipeline([
        ListingStatusFilter(),
        PriceFilter(min_price=args.min_price),
        LiquidityFilter(min_median_turnover=args.min_turnover, lookback_bars=20),
        HistoryFilter(min_history_bars=60),
        DataQualityFilter(max_missing_pct=0.05, lookback_bars=20),
    ])

    eligible, results = manager.get_eligible_universe(args.date, pipeline=pipeline)
    snap = manager.get_universe(args.date)

    rejection_counts: Dict[str, int] = {}
    for r in results:
        for reason in r.rejection_reasons:
            rejection_counts[reason] = rejection_counts.get(reason, 0) + 1

    print("\n" + "=" * 70)
    print("  APEX QUANT — NIFTY 500 UNIVERSE POINT-IN-TIME AUDIT")
    print("=" * 70)
    print(f"Universe Date:          {args.date}")
    print(f"Universe Source:        NIFTY 500 Index (NSE)")
    print(f"Point-in-Time Status:   {manager.point_in_time_status.value}")
    print(f"Total Constituents:     {snap.count}")
    print(f"Eligible for Trading:   {len(eligible)}")
    print(f"Rejected:               {len(results) - len(eligible)}")
    print("-" * 70)
    print("Rejection Breakdown:")
    if rejection_counts:
        for reason, count in rejection_counts.items():
            print(f"  • {reason:<35}: {count} stocks")
    else:
        print("  • None (All constituents eligible)")
    print("-" * 70)
    if eligible:
        print("Eligible Equities Sample: " + ", ".join([s.symbol for s in eligible[:15]]))
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
