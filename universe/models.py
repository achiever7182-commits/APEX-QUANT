"""
universe/models.py — Domain Models for Universe Management and Survivorship-Bias Protection.

Defines point-in-time constituent representations, stock metadata, universe snapshots,
and structured eligibility results with explicit rejection diagnostics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from core.interfaces.instrument import AssetClass, Exchange, Instrument


class ListingStatus(str, Enum):
    """Listing status of an equity on the exchange."""
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    DELISTED = "DELISTED"


class PointInTimeStatus(str, Enum):
    """Integrity status of historical universe constituent tracking."""
    POINT_IN_TIME_COMPLETE = "POINT_IN_TIME_COMPLETE"       # Complete historical coverage of the intended NIFTY 500 universe
    POINT_IN_TIME_SAMPLE = "POINT_IN_TIME_SAMPLE"           # Curated subset with accurate effective dates but incomplete coverage of full NIFTY 500
    POINT_IN_TIME_INCOMPLETE = "POINT_IN_TIME_INCOMPLETE"   # Insufficient historical membership information


@dataclass(frozen=True)
class Stock:
    """
    Asset-agnostic equity domain model.
    
    Attributes:
        symbol: Canonical uppercase symbol (e.g. 'RELIANCE', 'TCS')
        company_name: Full registered company name
        exchange: Exchange code (default 'NSE')
        isin: International Securities Identification Number (optional)
        sector: Broad economic sector (e.g. 'Financial Services', 'Energy')
        industry: Specific industry classification
        listing_status: ACTIVE, SUSPENDED, or DELISTED
        delisting_date: Date of delisting if applicable
        metadata: Extensible key-value metadata dictionary
    """
    symbol: str
    company_name: str
    exchange: str = "NSE"
    isin: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    listing_status: ListingStatus = ListingStatus.ACTIVE
    delisting_date: Optional[date] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        clean_sym = self.symbol.upper().replace(".NS", "").replace(".BO", "").strip()
        if not clean_sym:
            raise ValueError("Stock symbol cannot be empty.")
        object.__setattr__(self, "symbol", clean_sym)

    @property
    def is_tradable(self) -> bool:
        """True if the stock is actively listed."""
        return self.listing_status == ListingStatus.ACTIVE

    def is_tradable_on(self, as_of_date: Optional[Union[date, datetime, str]] = None) -> bool:
        """
        Evaluate if the equity was tradable as of a specific historical date.
        
        If as_of_date is None, returns current listing status (self.is_tradable).
        If delisted with an explicit delisting_date:
          - Returns True if as_of_date < delisting_date (was actively listed).
          - Returns False if as_of_date >= delisting_date.
        If suspended, returns False (current data model does not track historical suspension intervals).
        """
        if as_of_date is None:
            return self.is_tradable

        if isinstance(as_of_date, datetime):
            d = as_of_date.date()
        elif isinstance(as_of_date, str):
            d = datetime.fromisoformat(as_of_date.split("T")[0]).date()
        elif isinstance(as_of_date, date):
            d = as_of_date
        else:
            raise TypeError(f"Unsupported date type: {type(as_of_date)}")

        if self.listing_status == ListingStatus.DELISTED:
            if self.delisting_date is not None:
                return d < self.delisting_date
            return False

        if self.listing_status == ListingStatus.SUSPENDED:
            return False

        return self.listing_status == ListingStatus.ACTIVE

    def to_instrument(self, as_of_date: Optional[Union[date, datetime, str]] = None) -> Instrument:
        """
        Convert to core.interfaces.instrument.Instrument.
        
        If as_of_date is provided, instrument.is_tradable reflects the equity's listing status
        on that historical date rather than its present-day status.
        """
        tradable = self.is_tradable_on(as_of_date) if as_of_date is not None else self.is_tradable
        return Instrument(
            symbol=self.symbol,
            asset_class=AssetClass.EQUITY,
            exchange=Exchange.NSE if self.exchange == "NSE" else Exchange.BSE,
            currency="INR",
            lot_size=1.0,
            tick_size=0.05,
            isin=self.isin,
            is_tradable=tradable,
        )


@dataclass(frozen=True)
class UniverseMembership:
    """
    Tracks a stock's membership period in an index or universe.
    
    Guarantees point-in-time historical reconstruction.
    """
    symbol: str
    universe_name: str
    effective_from: date
    effective_to: Optional[date] = None  # None indicates stock is still a constituent
    notes: str = ""

    def __post_init__(self) -> None:
        clean_sym = self.symbol.upper().replace(".NS", "").replace(".BO", "").strip()
        object.__setattr__(self, "symbol", clean_sym)
        if self.effective_to and self.effective_from > self.effective_to:
            raise ValueError(f"effective_from ({self.effective_from}) cannot be after effective_to ({self.effective_to}) for {clean_sym}")

    def is_active_on(self, target_date: Union[date, datetime, str]) -> bool:
        """
        Check if the stock was an active member of the universe on target_date.
        """
        if isinstance(target_date, datetime):
            d = target_date.date()
        elif isinstance(target_date, str):
            d = datetime.fromisoformat(target_date.split("T")[0]).date()
        else:
            d = target_date

        if d < self.effective_from:
            return False
        if self.effective_to and d > self.effective_to:
            return False
        return True


@dataclass(frozen=True)
class UniverseSnapshot:
    """Immutable snapshot of universe constituents as of a specific date."""
    as_of_date: date
    universe_name: str
    constituents: List[Stock]
    point_in_time_status: PointInTimeStatus = PointInTimeStatus.POINT_IN_TIME_SAMPLE
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def count(self) -> int:
        return len(self.constituents)

    @property
    def symbols(self) -> List[str]:
        return [s.symbol for s in self.constituents]

    @property
    def catalog_size(self) -> int:
        return int(self.metadata.get("catalog_size", len(self.constituents)))

    @property
    def intended_universe_size(self) -> int:
        return int(self.metadata.get("intended_universe_size", 500))

    def get_by_symbol(self, symbol: str) -> Optional[Stock]:
        clean = symbol.upper().replace(".NS", "").strip()
        for s in self.constituents:
            if s.symbol == clean:
                return s
        return None


@dataclass
class EligibilityResult:
    """
    Structured outcome of evaluating a stock against eligibility filters.
    
    Provides human-readable, auditable reasons if rejected.
    """
    symbol: str
    is_eligible: bool
    rejection_reasons: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)

    def add_rejection(self, reason: str) -> None:
        """Record an explicit rejection reason and mark as ineligible."""
        self.is_eligible = False
        if reason not in self.rejection_reasons:
            self.rejection_reasons.append(reason)
