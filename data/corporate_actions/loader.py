"""
data/corporate_actions/loader.py — Corporate Action Storage and Cache Loader.

Handles serializing and retrieving symbol corporate actions from local disk/cache.
"""

from __future__ import annotations

from datetime import date, datetime
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from data.corporate_actions.models import CorporateAction, CorporateActionType

DEFAULT_ACTIONS_CACHE_DIR = Path("data_storage/processed/corporate_actions")


class CorporateActionsLoader:
    """Manages disk caching and retrieval of symbol corporate action histories."""

    def __init__(self, cache_dir: Optional[Path] = None) -> None:
        self.cache_dir = cache_dir or DEFAULT_ACTIONS_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_path(self, symbol: str) -> Path:
        clean = symbol.upper().replace(".NS", "").replace(".BO", "").strip()
        return self.cache_dir / f"{clean}.json"

    def save_actions(self, symbol: str, actions: List[CorporateAction]) -> Path:
        """Save list of corporate actions to JSON."""
        target = self._get_path(symbol)
        data = [
            {
                "symbol": a.symbol,
                "ex_date": str(a.ex_date_obj),
                "action_type": a.action_type.value,
                "ratio_numerator": a.ratio_numerator,
                "ratio_denominator": a.ratio_denominator,
                "value": a.value,
                "details": a.details,
            }
            for a in actions
        ]
        with open(target, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return target

    def load_actions(
        self,
        symbol: str,
        as_of_date: Optional[Union[date, datetime, str]] = None,
    ) -> List[CorporateAction]:
        """
        Load cached corporate actions for a symbol.
        
        Args:
            symbol: Ticker symbol
            as_of_date: If provided, returns only actions whose ex_date <= as_of_date.
                        If None, preserves default behavior of returning all cached actions.
        """
        target = self._get_path(symbol)
        if not target.exists():
            return []

        with open(target, "r", encoding="utf-8") as f:
            raw_list = json.load(f)

        actions: List[CorporateAction] = []
        for item in raw_list:
            actions.append(
                CorporateAction(
                    symbol=item["symbol"],
                    ex_date=item["ex_date"],
                    action_type=CorporateActionType(item["action_type"]),
                    ratio_numerator=float(item.get("ratio_numerator", 1.0)),
                    ratio_denominator=float(item.get("ratio_denominator", 1.0)),
                    value=float(item.get("value", 0.0)),
                    details=item.get("details", ""),
                )
            )

        if as_of_date is not None:
            actions = [a for a in actions if a.is_effective_on(as_of_date)]

        return actions
