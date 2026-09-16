"""
data/market/calendar.py — Indian Stock Market (NSE) Trading Calendar for APEX QUANT.

Enforces Indian market hours (09:15–15:30 IST), weekends, and statutory NSE exchange holidays.
Moves system away from 24/7 continuous crypto assumptions to realistic equity market hours.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Iterable, List, Optional, Set, Union
import zoneinfo

# Standard NSE Timezone
IST_ZONE = zoneinfo.ZoneInfo("Asia/Kolkata")

# Regular Trading Hours (Indian Standard Time)
NSE_MARKET_OPEN = time(9, 15, 0)
NSE_MARKET_CLOSE = time(15, 30, 0)

# Pre-Market Auction
NSE_PREMARKET_OPEN = time(9, 0, 0)
NSE_PREMARKET_CLOSE = time(9, 15, 0)

# Statutory NSE Trading Holidays (Official exchange holiday calendar 2020–2026)
NSE_HOLIDAYS_SET: Set[date] = {
    # 2020
    date(2020, 2, 21), date(2020, 3, 10), date(2020, 4, 2), date(2020, 4, 6),
    date(2020, 4, 10), date(2020, 4, 14), date(2020, 5, 1), date(2020, 5, 25),
    date(2020, 10, 2), date(2020, 11, 16), date(2020, 11, 30), date(2020, 12, 25),
    # 2021
    date(2021, 1, 26), date(2021, 3, 11), date(2021, 3, 29), date(2021, 4, 2),
    date(2021, 4, 14), date(2021, 4, 21), date(2021, 5, 13), date(2021, 7, 21),
    date(2021, 8, 19), date(2021, 9, 10), date(2021, 10, 15), date(2021, 11, 5),
    date(2021, 11, 19),
    # 2022
    date(2022, 1, 26), date(2022, 3, 1), date(2022, 3, 18), date(2022, 4, 14),
    date(2022, 4, 15), date(2022, 5, 3), date(2022, 8, 9), date(2022, 8, 15),
    date(2022, 8, 31), date(2022, 10, 5), date(2022, 10, 24), date(2022, 10, 26),
    date(2022, 11, 8),
    # 2023
    date(2023, 1, 26), date(2023, 3, 7), date(2023, 3, 30), date(2023, 4, 4),
    date(2023, 4, 7), date(2023, 4, 14), date(2023, 5, 1), date(2023, 6, 29),
    date(2023, 8, 15), date(2023, 9, 19), date(2023, 10, 2), date(2023, 10, 24),
    date(2023, 11, 14), date(2023, 11, 27), date(2023, 12, 25),
    # 2024
    date(2024, 1, 22), date(2024, 1, 26), date(2024, 3, 8), date(2024, 3, 25),
    date(2024, 3, 29), date(2024, 4, 11), date(2024, 4, 17), date(2024, 5, 1),
    date(2024, 5, 20), date(2024, 6, 17), date(2024, 7, 17), date(2024, 8, 15),
    date(2024, 10, 2), date(2024, 11, 1), date(2024, 11, 15), date(2024, 11, 20),
    date(2024, 12, 25),
    # 2025
    date(2025, 2, 26), date(2025, 3, 14), date(2025, 3, 31), date(2025, 4, 10),
    date(2025, 4, 14), date(2025, 4, 18), date(2025, 5, 1), date(2025, 8, 15),
    date(2025, 8, 27), date(2025, 10, 2), date(2025, 10, 21), date(2025, 10, 22),
    date(2025, 11, 5), date(2025, 12, 25),
    # 2026
    date(2026, 1, 26), date(2026, 3, 18), date(2026, 4, 3), date(2026, 4, 14),
    date(2026, 5, 1), date(2026, 5, 27), date(2026, 6, 16), date(2026, 8, 15),
    date(2026, 10, 2), date(2026, 10, 20), date(2026, 11, 9), date(2026, 11, 24),
    date(2026, 12, 25),
}


class NSEMarketCalendar:
    """
    Authoritative calendar for Indian National Stock Exchange (NSE).
    
    Provides methods to check market days, holidays, and regular trading sessions.
    """

    def __init__(self, custom_holidays: Optional[Set[date]] = None) -> None:
        self.holidays: Set[date] = custom_holidays if custom_holidays is not None else NSE_HOLIDAYS_SET

    @staticmethod
    def _to_date(dt: Union[date, datetime, str]) -> date:
        """Helper to convert date, datetime, or ISO string to date object."""
        if isinstance(dt, datetime):
            return dt.date()
        if isinstance(dt, date):
            return dt
        if isinstance(dt, str):
            # Parse YYYY-MM-DD
            return datetime.fromisoformat(dt.split("T")[0]).date()
        raise TypeError(f"Unsupported date type: {type(dt)}")

    def is_trading_day(self, dt: Union[date, datetime, str]) -> bool:
        """
        Check if a given date is an official NSE trading day.
        
        Returns False for weekends (Saturday/Sunday) and NSE holidays.
        """
        d = self._to_date(dt)
        # 5 = Saturday, 6 = Sunday
        if d.weekday() >= 5:
            return False
        if d in self.holidays:
            return False
        return True

    def get_trading_days(
        self,
        start_date: Union[date, datetime, str],
        end_date: Union[date, datetime, str],
    ) -> List[date]:
        """Return list of official NSE trading days between start_date and end_date (inclusive)."""
        start = self._to_date(start_date)
        end = self._to_date(end_date)
        if start > end:
            return []
        
        trading_days: List[date] = []
        curr = start
        while curr <= end:
            if self.is_trading_day(curr):
                trading_days.append(curr)
            curr += timedelta(days=1)
        return trading_days

    def is_market_open(self, dt: Optional[datetime] = None) -> bool:
        """
        Check if the NSE regular equity session is currently open at datetime dt.
        If dt is None, uses current local IST time.
        """
        if dt is None:
            now = datetime.now(IST_ZONE)
        else:
            if dt.tzinfo is None:
                now = dt.replace(tzinfo=IST_ZONE)
            else:
                now = dt.astimezone(IST_ZONE)

        if not self.is_trading_day(now.date()):
            return False

        t = now.time()
        return NSE_MARKET_OPEN <= t <= NSE_MARKET_CLOSE

    def get_missing_trading_days(
        self,
        actual_dates: Iterable[Union[date, datetime, str]],
        start_date: Optional[Union[date, datetime, str]] = None,
        end_date: Optional[Union[date, datetime, str]] = None,
    ) -> List[date]:
        """
        Compare a set/list of actual bar dates against official NSE calendar
        and return the dates that are missing.
        """
        act_set = {self._to_date(d) for d in actual_dates}
        if not act_set:
            return []

        s = self._to_date(start_date) if start_date else min(act_set)
        e = self._to_date(end_date) if end_date else max(act_set)

        expected = self.get_trading_days(s, e)
        missing = [d for d in expected if d not in act_set]
        return missing
