"""
universe/stock_filter.py — Composable Stock Screening and Eligibility Filter Engine for APEX QUANT.

Enforces price thresholds, turnover minimums, history depth, and data completeness.
Every rejection produces auditable, human-readable reason codes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple
import pandas as pd

from universe.liquidity import LiquidityEngine, LiquidityMetrics
from universe.models import EligibilityResult, ListingStatus, Stock


class IFilter(ABC):
    """Abstract interface for an individual eligibility filter."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Identifier for the filter."""
        raise NotImplementedError

    @abstractmethod
    def evaluate(
        self,
        stock: Stock,
        market_data_df: Optional[pd.DataFrame],
        as_of_date: date,
    ) -> Tuple[bool, Optional[str], Dict[str, Any]]:
        """
        Evaluate stock against this filter's criteria.
        
        Returns:
            Tuple of (is_passed: bool, rejection_reason: Optional[str], metric_details: Dict[str, Any])
        """
        raise NotImplementedError


class ListingStatusFilter(IFilter):
    """Ensures stock is actively listed on the evaluation date."""

    @property
    def name(self) -> str:
        return "ListingStatusFilter"

    def evaluate(
        self,
        stock: Stock,
        market_data_df: Optional[pd.DataFrame],
        as_of_date: date,
    ) -> Tuple[bool, Optional[str], Dict[str, Any]]:
        if stock.listing_status == ListingStatus.DELISTED:
            if stock.delisting_date and as_of_date >= stock.delisting_date:
                return False, "stock_delisted", {"listing_status": stock.listing_status.value}
        elif stock.listing_status == ListingStatus.SUSPENDED:
            return False, "stock_suspended", {"listing_status": stock.listing_status.value}

        return True, None, {"listing_status": stock.listing_status.value}


class PriceFilter(IFilter):
    """
    Screens against penny stocks and extreme high-priced oddities.
    Default minimum price: ₹10.0.
    """

    def __init__(self, min_price: float = 10.0, max_price: Optional[float] = None) -> None:
        self.min_price = min_price
        self.max_price = max_price

    @property
    def name(self) -> str:
        return "PriceFilter"

    def evaluate(
        self,
        stock: Stock,
        market_data_df: Optional[pd.DataFrame],
        as_of_date: date,
    ) -> Tuple[bool, Optional[str], Dict[str, Any]]:
        if market_data_df is None or market_data_df.empty:
            return False, "no_price_data", {}

        last_price = float(market_data_df["close"].iloc[-1])
        metrics = {"last_price": round(last_price, 2), "min_price": self.min_price}

        if last_price < self.min_price:
            return False, "price_below_minimum", metrics
        if self.max_price and last_price > self.max_price:
            return False, "price_above_maximum", metrics

        return True, None, metrics


class LiquidityFilter(IFilter):
    """
    Enforces minimum median daily turnover (default ₹5 Crore INR / ₹50,000,000).
    Ensures quantitative portfolio execution will not suffer catastrophic market impact.
    """

    def __init__(
        self,
        min_median_turnover: float = 50_000_000.0,  # ₹5 Crore INR
        lookback_bars: int = 20,
    ) -> None:
        self.min_median_turnover = min_median_turnover
        self.lookback_bars = lookback_bars

    @property
    def name(self) -> str:
        return "LiquidityFilter"

    def evaluate(
        self,
        stock: Stock,
        market_data_df: Optional[pd.DataFrame],
        as_of_date: date,
    ) -> Tuple[bool, Optional[str], Dict[str, Any]]:
        if market_data_df is None or market_data_df.empty:
            return False, "insufficient_liquidity_data", {}

        metrics = LiquidityEngine.calculate_metrics(stock.symbol, market_data_df, lookback_bars=self.lookback_bars)
        details = {
            "median_turnover": round(metrics.median_turnover, 2),
            "min_required_turnover": self.min_median_turnover,
            "lookback_bars": self.lookback_bars,
        }

        if metrics.median_turnover < self.min_median_turnover:
            return False, "median_turnover_below_threshold", details

        return True, None, details


class HistoryFilter(IFilter):
    """
    Requires minimum historical bars to allow meaningful rolling features (default 60 bars).
    """

    def __init__(self, min_history_bars: int = 60) -> None:
        self.min_history_bars = min_history_bars

    @property
    def name(self) -> str:
        return "HistoryFilter"

    def evaluate(
        self,
        stock: Stock,
        market_data_df: Optional[pd.DataFrame],
        as_of_date: date,
    ) -> Tuple[bool, Optional[str], Dict[str, Any]]:
        bars = len(market_data_df) if market_data_df is not None else 0
        details = {"available_bars": bars, "min_history_bars": self.min_history_bars}

        if bars < self.min_history_bars:
            return False, "insufficient_history", details

        return True, None, details


class DataQualityFilter(IFilter):
    """
    Rejects stocks where missing trading sessions exceed an acceptable threshold (default 5%).
    """

    def __init__(self, max_missing_pct: float = 0.05, lookback_bars: int = 20) -> None:
        self.max_missing_pct = max_missing_pct
        self.lookback_bars = lookback_bars

    @property
    def name(self) -> str:
        return "DataQualityFilter"

    def evaluate(
        self,
        stock: Stock,
        market_data_df: Optional[pd.DataFrame],
        as_of_date: date,
    ) -> Tuple[bool, Optional[str], Dict[str, Any]]:
        if market_data_df is None or market_data_df.empty:
            return False, "no_market_data", {}

        metrics = LiquidityEngine.calculate_metrics(stock.symbol, market_data_df, lookback_bars=self.lookback_bars)
        details = {"missing_pct": round(metrics.missing_percentage, 4), "max_allowed": self.max_missing_pct}

        if metrics.missing_percentage > self.max_missing_pct:
            return False, "missing_data_exceeds_threshold", details

        return True, None, details


class SectorFilter(IFilter):
    """Filters stocks by sector inclusion or exclusion lists."""

    def __init__(
        self,
        allowed_sectors: Optional[Set[str]] = None,
        excluded_sectors: Optional[Set[str]] = None,
    ) -> None:
        self.allowed_sectors = {s.lower() for s in allowed_sectors} if allowed_sectors else None
        self.excluded_sectors = {s.lower() for s in excluded_sectors} if excluded_sectors else set()

    @property
    def name(self) -> str:
        return "SectorFilter"

    def evaluate(
        self,
        stock: Stock,
        market_data_df: Optional[pd.DataFrame],
        as_of_date: date,
    ) -> Tuple[bool, Optional[str], Dict[str, Any]]:
        sec = (stock.sector or "Unknown").lower()
        details = {"sector": stock.sector}

        if self.allowed_sectors and sec not in self.allowed_sectors:
            return False, "sector_not_allowed", details
        if sec in self.excluded_sectors:
            return False, "sector_excluded", details

        return True, None, details


class StockFilterPipeline:
    """
    Orchestrates a sequential chain of filters, evaluating a stock and collecting diagnostic reasons.
    """

    def __init__(self, filters: Optional[Sequence[IFilter]] = None) -> None:
        if filters is not None:
            self.filters = list(filters)
        else:
            # Default standard institutional equity filter pipeline
            self.filters = [
                ListingStatusFilter(),
                PriceFilter(min_price=10.0),
                LiquidityFilter(min_median_turnover=50_000_000.0, lookback_bars=20),
                HistoryFilter(min_history_bars=60),
                DataQualityFilter(max_missing_pct=0.05, lookback_bars=20),
            ]

    def evaluate_stock(
        self,
        stock: Stock,
        market_data_df: Optional[pd.DataFrame],
        as_of_date: date,
    ) -> EligibilityResult:
        """
        Run all configured filters against the stock.
        Accumulates all reasons if multiple filters fail.
        """
        reasons: List[str] = []
        metrics: Dict[str, Any] = {}

        for flt in self.filters:
            passed, reason, flt_metrics = flt.evaluate(stock, market_data_df, as_of_date)
            metrics.update(flt_metrics)
            if not passed and reason:
                reasons.append(reason)

        is_eligible = (len(reasons) == 0)
        return EligibilityResult(
            symbol=stock.symbol,
            is_eligible=is_eligible,
            rejection_reasons=reasons,
            metrics=metrics,
        )
