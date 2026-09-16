"""
data/corporate_actions/adjuster.py — Deterministic Corporate Actions Adjustment Engine.

Calculates backward-adjusted prices and volumes for splits, bonus issues, and dividends.
CRITICAL: Raw prices are NEVER overwritten or mutated.
"""

from __future__ import annotations

from datetime import date
from typing import List, Sequence
import numpy as np
import pandas as pd

from data.corporate_actions.models import CorporateAction, CorporateActionType


class CorporateActionAdjuster:
    """
    Applies backward corporate action adjustments to historical price/volume series.
    
    Standard quantitative finance convention:
    - Recent prices after the corporate action match real trading quotes (factor = 1.0).
    - Historical prices before the ex-date are divided by the split factor.
    - Historical volumes before the ex-date are multiplied by the split factor.
    This preserves nominal contract value ($P \times V = \text{constant}$) and continuous returns.
    """

    @classmethod
    def adjust_historical_bars(
        cls,
        df: pd.DataFrame,
        corporate_actions: Sequence[CorporateAction],
        adjust_dividends: bool = False,
    ) -> pd.DataFrame:
        """
        Adjust raw OHLCV DataFrame with corporate actions.
        
        Args:
            df: DataFrame containing at minimum ['timestamp', 'open', 'high', 'low', 'close', 'volume']
            corporate_actions: List of CorporateAction objects for this symbol
            adjust_dividends: If True, also apply proportional dividend adjustments
            
        Returns:
            New DataFrame with raw prices intact plus new columns:
            ['adjusted_open', 'adjusted_high', 'adjusted_low', 'adjusted_close', 'adjusted_volume', 'adjustment_factor']
        """
        if df.empty:
            out = df.copy()
            for col in ["adjusted_open", "adjusted_high", "adjusted_low", "adjusted_close", "adjusted_volume", "adjustment_factor"]:
                out[col] = pd.Series(dtype="float64")
            return out

        out = df.copy()
        # Ensure timestamp is datetime and sorted
        if not pd.api.types.is_datetime64_any_dtype(out["timestamp"]):
            out["timestamp"] = pd.to_datetime(out["timestamp"])
        out = out.sort_values("timestamp").reset_index(drop=True)

        bar_dates = pd.to_datetime(out["timestamp"]).dt.date

        # Initialize adjustment factor array (1.0 for all bars by default)
        cum_split_factor = np.ones(len(out), dtype=np.float64)
        cum_div_factor = np.ones(len(out), dtype=np.float64)

        # Sort actions chronologically ascending
        sorted_actions = sorted(corporate_actions, key=lambda a: a.ex_date_obj)

        for action in sorted_actions:
            ex_d = action.ex_date_obj
            mask_before = bar_dates < ex_d

            if not np.any(mask_before):
                continue

            if action.action_type in (CorporateActionType.SPLIT, CorporateActionType.BONUS):
                mult = action.split_multiplier
                if mult > 0:
                    # Bars before ex_date need to be adjusted by dividing price by mult
                    # So cumulative split factor multiplies by mult
                    cum_split_factor[mask_before] *= mult

            elif action.action_type == CorporateActionType.DIVIDEND and adjust_dividends:
                div_val = action.value
                if div_val > 0:
                    # Proportional dividend adjustment:
                    # Find closing price on the bar immediately preceding ex-date
                    indices = np.where(mask_before)[0]
                    if len(indices) > 0:
                        last_idx = indices[-1]
                        pre_div_close = out.loc[last_idx, "close"]
                        if pre_div_close > div_val:
                            div_factor = (pre_div_close - div_val) / pre_div_close
                            cum_div_factor[mask_before] *= div_factor

        # Total price adjustment factor: P_adj = P_raw / total_factor
        total_price_factor = cum_split_factor / cum_div_factor

        # Populate adjusted columns
        out["adjustment_factor"] = total_price_factor
        out["adjusted_open"] = out["open"] / total_price_factor
        out["adjusted_high"] = out["high"] / total_price_factor
        out["adjusted_low"] = out["low"] / total_price_factor
        out["adjusted_close"] = out["close"] / total_price_factor
        # Volume is multiplied by the split factor so total turnover (P * V) remains invariant
        out["adjusted_volume"] = out["volume"] * cum_split_factor

        return out
