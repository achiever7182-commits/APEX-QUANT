"""
universe/constituents.py — Constituent Providers and Point-in-Time Membership Rosters.

Maintains historical effective date ranges for NIFTY 500 equities to eliminate survivorship bias.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
import json
from pathlib import Path
from typing import Dict, List, Optional

from universe.models import ListingStatus, PointInTimeStatus, Stock, UniverseMembership
from universe.sector import SectorCategory


class IConstituentsProvider(ABC):
    """Abstract provider of universe constituent lists and reconstitution histories."""

    @abstractmethod
    def get_stocks(self) -> List[Stock]:
        """Return full catalog of known stocks."""
        raise NotImplementedError

    @abstractmethod
    def get_memberships(self) -> List[UniverseMembership]:
        """Return historical membership spans with effective_from and effective_to dates."""
        raise NotImplementedError

    @abstractmethod
    def get_point_in_time_status(self) -> PointInTimeStatus:
        """Return whether reconstitution records are complete or partial."""
        raise NotImplementedError


class CuratedNifty500Provider(IConstituentsProvider):
    """
    Curated repository of NIFTY 500 constituents with explicit reconstitution events.
    
    Includes representative equities across all 11 NSE sectors, along with
    historical additions, index removals, and delisting events.
    """

    def __init__(self) -> None:
        self._stocks: Dict[str, Stock] = {}
        self._memberships: List[UniverseMembership] = []
        self._initialize_curated_data()

    def _initialize_curated_data(self) -> None:
        # 1. Benchmark Leaders & Major NIFTY 500 Constituents
        stock_specs = [
            # Financial Services
            ("HDFCBANK", "HDFC Bank Limited", "INE040A01034", SectorCategory.FINANCIAL_SERVICES.value, "Private Bank"),
            ("ICICIBANK", "ICICI Bank Limited", "INE090A01021", SectorCategory.FINANCIAL_SERVICES.value, "Private Bank"),
            ("SBIN", "State Bank of India", "INE062A01020", SectorCategory.FINANCIAL_SERVICES.value, "Public Bank"),
            ("KOTAKBANK", "Kotak Mahindra Bank Limited", "INE237A01028", SectorCategory.FINANCIAL_SERVICES.value, "Private Bank"),
            ("AXISBANK", "Axis Bank Limited", "INE238A01034", SectorCategory.FINANCIAL_SERVICES.value, "Private Bank"),
            ("BAJFINANCE", "Bajaj Finance Limited", "INE296A01024", SectorCategory.FINANCIAL_SERVICES.value, "NBFC"),
            ("JIOFIN", "Jio Financial Services Limited", "INE758E01017", SectorCategory.FINANCIAL_SERVICES.value, "Financial Services"),
            # Information Technology
            ("TCS", "Tata Consultancy Services Limited", "INE467B01029", SectorCategory.INFORMATION_TECHNOLOGY.value, "IT Services"),
            ("INFY", "Infosys Limited", "INE009A01021", SectorCategory.INFORMATION_TECHNOLOGY.value, "IT Services"),
            ("HCLTECH", "HCL Technologies Limited", "INE860A01027", SectorCategory.INFORMATION_TECHNOLOGY.value, "IT Services"),
            ("WIPRO", "Wipro Limited", "INE075A01034", SectorCategory.INFORMATION_TECHNOLOGY.value, "IT Services"),
            ("TECHM", "Tech Mahindra Limited", "INE669C01036", SectorCategory.INFORMATION_TECHNOLOGY.value, "IT Services"),
            ("LTIM", "LTIMindtree Limited", "INE214T01019", SectorCategory.INFORMATION_TECHNOLOGY.value, "IT Services"),
            # Energy & Oil/Gas
            ("RELIANCE", "Reliance Industries Limited", "INE002A01018", SectorCategory.ENERGY.value, "Oil & Gas Refineries"),
            ("ONGC", "Oil and Natural Gas Corporation Limited", "INE213A01029", SectorCategory.ENERGY.value, "Oil Exploration"),
            ("BPCL", "Bharat Petroleum Corporation Limited", "INE029A01011", SectorCategory.ENERGY.value, "Oil & Gas"),
            ("IOC", "Indian Oil Corporation Limited", "INE242A01010", SectorCategory.ENERGY.value, "Oil & Gas"),
            # Consumer Goods & FMCG
            ("ITC", "ITC Limited", "INE154A01025", SectorCategory.CONSUMER_GOODS.value, "Diversified FMCG"),
            ("HINDUNILVR", "Hindustan Unilever Limited", "INE030A01027", SectorCategory.CONSUMER_GOODS.value, "FMCG"),
            ("NESTLEIND", "Nestle India Limited", "INE239A01016", SectorCategory.CONSUMER_GOODS.value, "Food Products"),
            ("BRITANNIA", "Britannia Industries Limited", "INE216A01030", SectorCategory.CONSUMER_GOODS.value, "Food Products"),
            ("TATACONSUM", "Tata Consumer Products Limited", "INE192A01025", SectorCategory.CONSUMER_GOODS.value, "Tea & Coffee"),
            ("TITAN", "Titan Company Limited", "INE280A01028", SectorCategory.CONSUMER_GOODS.value, "Gems & Jewellery"),
            ("TRENT", "Trent Limited", "INE849A01020", SectorCategory.CONSUMER_GOODS.value, "Retail"),
            # Automobile
            ("TATAMOTORS", "Tata Motors Limited", "INE155A01022", SectorCategory.AUTOMOBILE.value, "Automobiles"),
            ("MARUTI", "Maruti Suzuki India Limited", "INE585B01010", SectorCategory.AUTOMOBILE.value, "Passenger Cars"),
            ("M&M", "Mahindra & Mahindra Limited", "INE101A01026", SectorCategory.AUTOMOBILE.value, "Commercial Vehicles"),
            ("BAJAJ-AUTO", "Bajaj Auto Limited", "INE917I01010", SectorCategory.AUTOMOBILE.value, "2 & 3 Wheelers"),
            ("EICHERMOT", "Eicher Motors Limited", "INE066A01013", SectorCategory.AUTOMOBILE.value, "2 Wheelers"),
            # Healthcare & Pharma
            ("SUNPHARMA", "Sun Pharmaceutical Industries Limited", "INE044A01036", SectorCategory.HEALTHCARE.value, "Pharmaceuticals"),
            ("CIPLA", "Cipla Limited", "INE059A01026", SectorCategory.HEALTHCARE.value, "Pharmaceuticals"),
            ("DRREDDY", "Dr. Reddy's Laboratories Limited", "INE089A01023", SectorCategory.HEALTHCARE.value, "Pharmaceuticals"),
            ("DIVISLAB", "Divi's Laboratories Limited", "INE361B01024", SectorCategory.HEALTHCARE.value, "Active Pharma"),
            ("APOLLOHOSP", "Apollo Hospitals Enterprise Limited", "INE437A01024", SectorCategory.HEALTHCARE.value, "Healthcare Services"),
            # Industrials & Capital Goods
            ("LT", "Larsen & Toubro Limited", "INE018A01030", SectorCategory.INDUSTRIALS.value, "Engineering & Construction"),
            ("BEL", "Bharat Electronics Limited", "INE263A01024", SectorCategory.INDUSTRIALS.value, "Aerospace & Defense"),
            ("HAL", "Hindustan Aeronautics Limited", "INE066F01012", SectorCategory.INDUSTRIALS.value, "Aerospace & Defense"),
            ("SIEMENS", "Siemens Limited", "INE003A01024", SectorCategory.INDUSTRIALS.value, "Industrial Equipment"),
            # Materials & Metals
            ("TATASTEEL", "Tata Steel Limited", "INE081A01020", SectorCategory.MATERIALS.value, "Iron & Steel"),
            ("JSWSTEEL", "JSW Steel Limited", "INE019A01038", SectorCategory.MATERIALS.value, "Iron & Steel"),
            ("HINDALCO", "Hindalco Industries Limited", "INE038A01020", SectorCategory.MATERIALS.value, "Aluminium"),
            ("GRASIM", "Grasim Industries Limited", "INE047A01021", SectorCategory.MATERIALS.value, "Cement"),
            ("ULTRACEMCO", "UltraTech Cement Limited", "INE481G01011", SectorCategory.MATERIALS.value, "Cement"),
            # Utilities & Power
            ("NTPC", "NTPC Limited", "INE733E01010", SectorCategory.UTILITIES.value, "Power Generation"),
            ("POWERGRID", "Power Grid Corporation of India Limited", "INE752E01010", SectorCategory.UTILITIES.value, "Power Transmission"),
            ("COALINDIA", "Coal India Limited", "INE522F01014", SectorCategory.UTILITIES.value, "Coal Extraction"),
            # Communication Services
            ("BHARTIARTL", "Bharti Airtel Limited", "INE397D01024", SectorCategory.COMMUNICATION_SERVICES.value, "Telecom Services"),
            # Infrastructure
            ("ADANIPORTS", "Adani Ports and Special Economic Zone Limited", "INE742F01042", SectorCategory.INDUSTRIALS.value, "Ports"),
            ("ADANIENT", "Adani Enterprises Limited", "INE423A01024", SectorCategory.MATERIALS.value, "Metals & Mining"),
        ]

        # Register Active Stocks
        for sym, name, isin, sector, ind in stock_specs:
            self._stocks[sym] = Stock(
                symbol=sym,
                company_name=name,
                exchange="NSE",
                isin=isin,
                sector=sector,
                industry=ind,
                listing_status=ListingStatus.ACTIVE,
            )
            # Default membership: from Jan 1, 2020 onward (unless overridden below)
            eff_from = date(2023, 8, 21) if sym == "JIOFIN" else date(2020, 1, 1)
            self._memberships.append(
                UniverseMembership(
                    symbol=sym,
                    universe_name="NIFTY500",
                    effective_from=eff_from,
                    effective_to=None,
                    notes="Active constituent",
                )
            )

        # 2. Reconstitution Edge Cases (Removed / Merged / Delisted Stocks for Historical Point-in-Time Testing)
        # Case A: HDFCLTD (Merged into HDFCBANK on July 13, 2023)
        self._stocks["HDFCLTD"] = Stock(
            symbol="HDFCLTD",
            company_name="Housing Development Finance Corporation Limited",
            exchange="NSE",
            isin="INE001A01036",
            sector=SectorCategory.FINANCIAL_SERVICES.value,
            industry="Housing Finance",
            listing_status=ListingStatus.DELISTED,
            delisting_date=date(2023, 7, 13),
        )
        self._memberships.append(
            UniverseMembership(
                symbol="HDFCLTD",
                universe_name="NIFTY500",
                effective_from=date(2020, 1, 1),
                effective_to=date(2023, 7, 12),
                notes="Delisted on July 13, 2023 due to amalgamation with HDFC Bank",
            )
        )

        # Case B: YESBANK (Historical constituent removed from major benchmark index on March 27, 2020)
        self._stocks["YESBANK"] = Stock(
            symbol="YESBANK",
            company_name="Yes Bank Limited",
            exchange="NSE",
            isin="INE528G01035",
            sector=SectorCategory.FINANCIAL_SERVICES.value,
            industry="Private Bank",
            listing_status=ListingStatus.ACTIVE,
        )
        self._memberships.append(
            UniverseMembership(
                symbol="YESBANK",
                universe_name="NIFTY500",
                effective_from=date(2020, 1, 1),
                effective_to=date(2020, 3, 26),
                notes="Removed from premier index during reconstruction",
            )
        )

        # Case C: DHFL (Delisted housing finance firm)
        self._stocks["DHFL"] = Stock(
            symbol="DHFL",
            company_name="Dewan Housing Finance Corporation Limited",
            exchange="NSE",
            isin="INE202B01012",
            sector=SectorCategory.FINANCIAL_SERVICES.value,
            industry="Housing Finance",
            listing_status=ListingStatus.DELISTED,
            delisting_date=date(2021, 6, 14),
        )
        self._memberships.append(
            UniverseMembership(
                symbol="DHFL",
                universe_name="NIFTY500",
                effective_from=date(2020, 1, 1),
                effective_to=date(2021, 6, 13),
                notes="Insolvency resolution and delisting",
            )
        )

    def get_stocks(self) -> List[Stock]:
        return list(self._stocks.values())

    def get_memberships(self) -> List[UniverseMembership]:
        return self._memberships

    def get_point_in_time_status(self) -> PointInTimeStatus:
        return PointInTimeStatus.POINT_IN_TIME_SAMPLE


class JSONConstituentsProvider(IConstituentsProvider):
    """Loads universe constituents and reconstitution dates from an external JSON file."""

    def __init__(self, file_path: Union[str, Path]) -> None:
        self.file_path = Path(file_path)
        self._stocks: List[Stock] = []
        self._memberships: List[UniverseMembership] = []
        self._is_complete = False
        self._load()

    def _load(self) -> None:
        if not self.file_path.exists():
            raise FileNotFoundError(f"Constituent file not found: {self.file_path}")

        with open(self.file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self._is_complete = data.get("point_in_time_complete", False)
        for s in data.get("stocks", []):
            self._stocks.append(
                Stock(
                    symbol=s["symbol"],
                    company_name=s.get("company_name", s["symbol"]),
                    exchange=s.get("exchange", "NSE"),
                    isin=s.get("isin"),
                    sector=s.get("sector"),
                    industry=s.get("industry"),
                    listing_status=ListingStatus(s.get("listing_status", "ACTIVE")),
                )
            )

        for m in data.get("memberships", []):
            eff_to = date.fromisoformat(m["effective_to"]) if m.get("effective_to") else None
            self._memberships.append(
                UniverseMembership(
                    symbol=m["symbol"],
                    universe_name=m.get("universe_name", "NIFTY500"),
                    effective_from=date.fromisoformat(m["effective_from"]),
                    effective_to=eff_to,
                    notes=m.get("notes", ""),
                )
            )

    def get_stocks(self) -> List[Stock]:
        return self._stocks

    def get_memberships(self) -> List[UniverseMembership]:
        return self._memberships

    def get_point_in_time_status(self) -> PointInTimeStatus:
        return PointInTimeStatus.POINT_IN_TIME_COMPLETE if self._is_complete else PointInTimeStatus.POINT_IN_TIME_INCOMPLETE
