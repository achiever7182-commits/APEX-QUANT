"""
universe/nifty500.py — NIFTY 500 Index Repository and Query Engine for APEX QUANT.

Manages the broad-market Indian equity universe with sector groupings and historical point-in-time membership.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Dict, List, Optional, Set, Union

from universe.constituents import CuratedNifty500Provider, IConstituentsProvider
from universe.models import PointInTimeStatus, Stock, UniverseMembership, UniverseSnapshot
from universe.sector import SectorCategory


class Nifty500:
    """
    NIFTY 500 Index constituent and sector management.
    """

    def __init__(self, provider: Optional[IConstituentsProvider] = None) -> None:
        self.provider = provider or CuratedNifty500Provider()
        self._stocks_by_symbol: Dict[str, Stock] = {s.symbol: s for s in self.provider.get_stocks()}
        self._memberships: List[UniverseMembership] = self.provider.get_memberships()

    @property
    def total_catalog_count(self) -> int:
        """Total distinct stocks registered in repository across all time."""
        return len(self._stocks_by_symbol)

    @property
    def point_in_time_status(self) -> PointInTimeStatus:
        return self.provider.get_point_in_time_status()

    def get_stock(self, symbol: str) -> Optional[Stock]:
        """Fetch stock metadata by symbol."""
        clean = symbol.upper().replace(".NS", "").strip()
        return self._stocks_by_symbol.get(clean)

    def get_all_symbols(self) -> List[str]:
        """Return all distinct symbols registered in repository across all time."""
        return sorted(self._stocks_by_symbol.keys())

    def get_point_in_time_constituents(self, as_of_date: Union[date, datetime, str]) -> UniverseSnapshot:
        """
        Reconstruct NIFTY 500 constituents strictly on as_of_date.
        
        Guarantees that a stock added after as_of_date or removed before as_of_date is excluded.
        """
        if isinstance(as_of_date, datetime):
            target_d = as_of_date.date()
        elif isinstance(as_of_date, str):
            target_d = datetime.fromisoformat(as_of_date.split("T")[0]).date()
        else:
            target_d = as_of_date

        active_symbols: Set[str] = set()
        for m in self._memberships:
            if m.is_active_on(target_d):
                active_symbols.add(m.symbol)

        active_stocks: List[Stock] = []
        for sym in sorted(active_symbols):
            stock = self._stocks_by_symbol.get(sym)
            if stock:
                active_stocks.append(stock)

        return UniverseSnapshot(
            as_of_date=target_d,
            universe_name="NIFTY500_CURATED_SAMPLE",
            constituents=active_stocks,
            point_in_time_status=self.point_in_time_status,
            metadata={
                "catalog_size": len(self._stocks_by_symbol),
                "intended_universe_size": 500,
                "is_curated_sample": True,
            },
        )

    def get_stocks_by_sector(self, sector: Union[SectorCategory, str]) -> List[Stock]:
        """Return all stocks matching a specific sector."""
        sec_val = sector.value if isinstance(sector, SectorCategory) else str(sector).strip()
        return [s for s in self._stocks_by_symbol.values() if s.sector and s.sector.lower() == sec_val.lower()]
