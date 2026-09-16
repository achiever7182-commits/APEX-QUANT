"""
core/interfaces/universe.py — Multi-Asset Universe Management Interface for APEX QUANT.

Provides the contract for defining, scanning, and dynamically filtering a universe of
equities (such as the NIFTY 500) before passing them to feature engineering and ranking.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Set

from core.interfaces.instrument import Instrument


@dataclass
class UniverseFilter:
    """Filter criteria to prune untradeable or illiquid instruments."""
    min_median_volume_20d: float = 50_000.0   # Minimum daily share volume
    min_median_turnover_20d: float = 10_000_000.0 # Min daily turnover (1 Crore INR)
    min_price: float = 10.0                   # Filter penny stocks
    max_price: Optional[float] = None
    exclude_asm_gsm: bool = True              # Exclude surveillance list stocks (NSE ASM/GSM)
    allowed_sectors: Optional[Set[str]] = None
    excluded_symbols: Set[str] = field(default_factory=set)


class IUniverseManager(ABC):
    """
    Abstract Universe Manager.
    
    Subclasses will implement:
    - Nifty500UniverseManager
    - CryptoUniverseManager (legacy single/multi-pair)
    - CustomListUniverseManager
    """

    @abstractmethod
    def get_all_symbols(self) -> List[str]:
        """Return the raw list of all symbols in the universe."""
        raise NotImplementedError

    @abstractmethod
    def get_tradable_instruments(self, filter_criteria: Optional[UniverseFilter] = None) -> List[Instrument]:
        """Return filtered instruments that qualify for trading."""
        raise NotImplementedError

    @abstractmethod
    def update_constituents(self) -> None:
        """Refresh universe constituents from exchange / index provider."""
        raise NotImplementedError
