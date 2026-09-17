"""
ranking/filters.py — Eligibility Filters and Failure Diagnostics for Stock Ranking.

Separates ELIGIBLE from INELIGIBLE stocks prior to cross-sectional ranking.
Guarantees every excluded asset receives a deterministic, transparent RejectionReason.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, Optional, Set, Tuple
import numpy as np
import pandas as pd

from ranking.config import RankingConfig
from ranking.models import RejectionReason
from universe.models import ListingStatus


class EligibilityFilter:
    """
    Evaluates an instrument's data row against quantitative eligibility criteria.
    """

    def __init__(self, config: Optional[RankingConfig] = None):
        self.config = config or RankingConfig()

    def evaluate_candidate(
        self,
        symbol: str,
        row_data: Dict[str, Any],
        active_universe_symbols: Optional[Set[str]] = None,
    ) -> Tuple[bool, Optional[RejectionReason]]:
        """
        Determine if an asset is eligible for ranking at the evaluation timestamp.

        Parameters:
            symbol: Ticker symbol.
            row_data: Dict containing features, prices, predictions, and status flags.
            active_universe_symbols: Set of active symbols on evaluation date (from Step 3 PIT universe).

        Returns:
            Tuple of (is_eligible: bool, rejection_reason: Optional[RejectionReason])
        """
        # 1. Point-in-time universe membership
        if active_universe_symbols is not None and symbol not in active_universe_symbols:
            return False, RejectionReason.NOT_IN_UNIVERSE

        # 2. Delisting / Listing status
        listing_status = row_data.get("listing_status")
        if listing_status == ListingStatus.DELISTED.value or listing_status == "DELISTED":
            return False, RejectionReason.DELISTED

        # 3. Valid price check (if close price is present in candidate data)
        if "close" in row_data:
            close = row_data.get("close")
            if close is None or pd.isna(close) or float(close) <= 0.0 or np.isinf(close):
                return False, RejectionReason.INVALID_PRICE

        # 4. Sufficient feature history
        suff_hist = row_data.get("has_sufficient_history", True)
        if suff_hist is False or suff_hist == 0:
            return False, RejectionReason.INSUFFICIENT_HISTORY

        # 5. Valid ML prediction
        pred = row_data.get("predicted_return")
        if pred is None or pd.isna(pred) or np.isinf(pred):
            return False, RejectionReason.MISSING_PREDICTION

        # 6. Minimum predicted return threshold (optional)
        if self.config.min_predicted_return is not None:
            if float(pred) < self.config.min_predicted_return:
                return False, RejectionReason.BELOW_SCORE_THRESHOLD

        # 7. Minimum liquidity threshold (optional)
        if self.config.min_median_turnover is not None:
            turnover = row_data.get("turnover_sma_20d", row_data.get("turnover"))
            if turnover is None or pd.isna(turnover) or float(turnover) < self.config.min_median_turnover:
                return False, RejectionReason.LOW_LIQUIDITY

        # 8. Maximum volatility ceiling (optional)
        if self.config.max_volatility is not None:
            vol = row_data.get("volatility_20d", row_data.get("volatility_10d"))
            if vol is not None and not pd.isna(vol) and float(vol) > self.config.max_volatility:
                return False, RejectionReason.HIGH_VOLATILITY

        return True, None
