"""
data/corporate_actions/models.py — Corporate Action Models for APEX QUANT.

Defines corporate actions (Splits, Bonus issues, Rights, Dividends) enabling
deterministic historical price adjustment to prevent artificial ML signal shocks.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Optional, Union


class CorporateActionType(str, Enum):
    SPLIT = "SPLIT"
    BONUS = "BONUS"
    RIGHTS = "RIGHTS"
    DIVIDEND = "DIVIDEND"


@dataclass(frozen=True)
class CorporateAction:
    """
    Representation of an individual corporate action event.
    
    Attributes:
        symbol: Canonical ticker symbol (e.g. 'RELIANCE', 'TCS')
        ex_date: The ex-date of the corporate action (date or YYYY-MM-DD string)
        action_type: Type of action (SPLIT, BONUS, RIGHTS, DIVIDEND)
        ratio_numerator: Numerator of the split/bonus ratio (e.g., 2.0 in a 2:1 split)
        ratio_denominator: Denominator of the ratio (e.g., 1.0 in a 2:1 split)
        value: Monetary value per share (for DIVIDEND or RIGHTS price)
        details: Human-readable description
    """
    symbol: str
    ex_date: Union[date, str]
    action_type: CorporateActionType
    ratio_numerator: float = 1.0
    ratio_denominator: float = 1.0
    value: float = 0.0
    details: str = ""

    def __post_init__(self) -> None:
        clean_symbol = self.symbol.upper().replace(".NS", "").replace(".BO", "").strip()
        object.__setattr__(self, "symbol", clean_symbol)

    @property
    def ex_date_obj(self) -> date:
        """Return ex_date as a datetime.date object."""
        if isinstance(self.ex_date, date):
            return self.ex_date
        return datetime.fromisoformat(str(self.ex_date).split("T")[0]).date()

    @property
    def split_multiplier(self) -> float:
        """
        Multiplicative factor by which share count increases on/after ex_date.
        For a 2:1 split (old share becomes 2 new shares), multiplier = 2.0.
        For a 1:1 bonus (1 bonus share for every 1 existing share, total 2 shares), multiplier = 2.0.
        For a 1:2 reverse split, multiplier = 0.5.
        """
        if self.action_type == CorporateActionType.SPLIT:
            if self.ratio_denominator <= 0:
                raise ValueError(f"Invalid split denominator: {self.ratio_denominator}")
            return float(self.ratio_numerator) / float(self.ratio_denominator)
        
        elif self.action_type == CorporateActionType.BONUS:
            # Bonus ratio X:Y means X new shares for Y existing shares -> multiplier = (X + Y) / Y
            if self.ratio_denominator <= 0:
                raise ValueError(f"Invalid bonus denominator: {self.ratio_denominator}")
            return (float(self.ratio_numerator) + float(self.ratio_denominator)) / float(self.ratio_denominator)
        
        return 1.0
