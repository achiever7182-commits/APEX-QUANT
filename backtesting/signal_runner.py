"""
backtesting/signal_runner.py — Point-in-time signal and ranking orchestration.

Consumes Step 6 CrossSectionalRanker to produce RankedUniverse at timestamp T.
Reuses existing Step 6 ranking architecture with zero logic duplication.
"""
from __future__ import annotations

from typing import Optional
import pandas as pd

from ranking.models import RankedUniverse
from ranking.ranker import CrossSectionalRanker
from ranking.config import RankingConfig
from universe.universe_manager import UniverseManager


class SignalRunner:
    """
    Executes cross-sectional ranking at evaluation timestamp T.
    Directly wraps Step 6 CrossSectionalRanker.
    """

    def __init__(
        self,
        ranker: Optional[CrossSectionalRanker] = None,
        config: Optional[RankingConfig] = None,
        universe_manager: Optional[UniverseManager] = None,
    ) -> None:
        if ranker is not None:
            self.ranker = ranker
        else:
            r_cfg = config or RankingConfig()
            u_mgr = universe_manager or UniverseManager()
            self.ranker = CrossSectionalRanker(config=r_cfg, universe_manager=u_mgr)

    def generate_ranking(
        self,
        candidate_panel: pd.DataFrame,
        as_of_time: pd.Timestamp,
    ) -> RankedUniverse:
        """
        Generate point-in-time RankedUniverse for as_of_time.

        Parameters:
            candidate_panel: Cross-sectional dataframe containing features, predictions,
                             and market state at as_of_time.
            as_of_time: Target evaluation timestamp.

        Returns:
            RankedUniverse snapshot.
        """
        # Filter candidate panel strictly to as_of_time
        panel_c = candidate_panel.copy()
        panel_c["timestamp"] = pd.to_datetime(panel_c["timestamp"])

        if as_of_time.tzinfo is not None and panel_c["timestamp"].dt.tz is None:
            slice_df = panel_c[panel_c["timestamp"].dt.date == as_of_time.tz_localize(None).date()]
        elif as_of_time.tzinfo is None and panel_c["timestamp"].dt.tz is not None:
            slice_df = panel_c[panel_c["timestamp"].dt.tz_localize(None).dt.date == as_of_time.date()]
        else:
            slice_df = panel_c[panel_c["timestamp"].dt.date == as_of_time.date()]

        sector_lookup = None
        if "sector" in slice_df.columns:
            sector_lookup = {
                row["symbol"]: row["sector"]
                for _, row in slice_df.drop_duplicates(subset=["symbol"]).iterrows()
                if pd.notna(row["sector"])
            }

        dt_str = as_of_time.strftime("%Y-%m-%d")
        return self.ranker.rank_cross_section(
            slice_df,
            as_of_date=dt_str,
            sector_lookup=sector_lookup,
        )
