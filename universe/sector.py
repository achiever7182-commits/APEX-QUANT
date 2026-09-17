"""
universe/sector.py — Standardized Sectoral Classifications for Indian Equities.

Provides canonical sector hierarchies aligned with National Stock Exchange (NSE) indices.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Set


class SectorCategory(str, Enum):
    """Standard NSE broad economic sector classifications."""
    FINANCIAL_SERVICES = "Financial Services"
    INFORMATION_TECHNOLOGY = "Information Technology"
    ENERGY = "Energy"
    CONSUMER_GOODS = "Consumer Goods"
    HEALTHCARE = "Healthcare"
    AUTOMOBILE = "Automobile"
    INDUSTRIALS = "Industrials"
    MATERIALS = "Materials"
    UTILITIES = "Utilities"
    COMMUNICATION_SERVICES = "Communication Services"
    REAL_ESTATE = "Real Estate"
    DIVERSIFIED = "Diversified"
    UNKNOWN = "Unknown"


@dataclass(frozen=True)
class SectorInfo:
    """Metadata regarding an equity's sector and source of classification."""
    sector: SectorCategory
    industry: Optional[str] = None
    classification_source: str = "NSE_OFFICIAL"

    @classmethod
    def from_string(cls, sector_str: Optional[str], industry: Optional[str] = None, source: str = "NSE_OFFICIAL") -> SectorInfo:
        if not sector_str:
            return cls(sector=SectorCategory.UNKNOWN, industry=industry, classification_source=source)

        normalized = sector_str.strip().lower()
        for cat in SectorCategory:
            if cat.value.lower() == normalized:
                return cls(sector=cat, industry=industry, classification_source=source)
            if normalized in cat.value.lower():
                return cls(sector=cat, industry=industry, classification_source=source)

        # Fallback mappings
        mapping = {
            "finance": SectorCategory.FINANCIAL_SERVICES,
            "banking": SectorCategory.FINANCIAL_SERVICES,
            "it": SectorCategory.INFORMATION_TECHNOLOGY,
            "tech": SectorCategory.INFORMATION_TECHNOLOGY,
            "oil": SectorCategory.ENERGY,
            "fmcg": SectorCategory.CONSUMER_GOODS,
            "pharma": SectorCategory.HEALTHCARE,
            "auto": SectorCategory.AUTOMOBILE,
            "metals": SectorCategory.MATERIALS,
            "telecom": SectorCategory.COMMUNICATION_SERVICES,
            "power": SectorCategory.UTILITIES,
        }
        for key, cat in mapping.items():
            if key in normalized:
                return cls(sector=cat, industry=industry, classification_source=source)

        return cls(sector=SectorCategory.UNKNOWN, industry=industry, classification_source=source)


ALL_SECTORS: List[SectorCategory] = [s for s in SectorCategory if s != SectorCategory.UNKNOWN]
