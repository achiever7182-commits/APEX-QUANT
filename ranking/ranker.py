"""
ranking/ranker.py — Cross-Sectional Stock Ranker Orchestrator.

Orchestrates:
  1. Point-in-time universe check and eligibility filtering (ranking/filters.py)
  2. Multi-factor cross-sectional scoring (ranking/scoring.py)
  3. Deterministic tie-breaking:
     - 1. opportunity_score (descending)
     - 2. predicted_return (descending)
     - 3. symbol (ascending alphabetical)
  4. Top-K cutoff filtering
  5. Sector and industry metadata preservation
  6. Output generation: RankedUniverse container & tabular representation
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence, Set, Union
import numpy as np
import pandas as pd

from ranking.config import RankingConfig
from ranking.filters import EligibilityFilter
from ranking.models import (
    OpportunityRank,
    RankedUniverse,
    RejectionReason,
    ScoringComponents,
)
from ranking.scoring import OpportunityScorer
from universe.universe_manager import UniverseManager

logger = logging.getLogger("apex_quant.ranking")


class CrossSectionalRanker:
    """
    Production cross-sectional ranking engine for APEX QUANT Indian equities.
    """

    def __init__(
        self,
        config: Optional[RankingConfig] = None,
        universe_manager: Optional[UniverseManager] = None,
    ):
        self.config = config or RankingConfig()
        self.universe_manager = universe_manager
        self.filter_engine = EligibilityFilter(config=self.config)
        self.scorer = OpportunityScorer(config=self.config)

    def rank_cross_section(
        self,
        df_candidates: pd.DataFrame,
        as_of_date: Optional[Union[str, pd.Timestamp]] = None,
        sector_lookup: Optional[Dict[str, str]] = None,
        industry_lookup: Optional[Dict[str, str]] = None,
    ) -> RankedUniverse:
        """
        Rank candidate stocks at a single timestamp.

        Parameters:
            df_candidates: DataFrame containing candidate stocks with features and 'predicted_return'.
            as_of_date: Evaluation timestamp/date. If None, inferred from df_candidates['timestamp'].
            sector_lookup: Optional mapping of symbol -> sector. If None, queried from UniverseManager.
            industry_lookup: Optional mapping of symbol -> industry.

        Returns:
            RankedUniverse containing all candidates with eligibility, scores, ranks, and diagnostics.
        """
        if df_candidates.empty:
            eval_ts = pd.to_datetime(as_of_date) if as_of_date else pd.Timestamp.now()
            return RankedUniverse(
                timestamp=eval_ts,
                ranked_items=[],
                total_evaluated=0,
                eligible_count=0,
                rejected_count=0,
                top_k=self.config.top_k,
            )

        # Invalidate multiple timestamps (rank_cross_section operates on a single timestamp slice)
        timestamps = df_candidates["timestamp"].unique()
        if len(timestamps) > 1 and as_of_date is None:
            raise ValueError(
                f"df_candidates contains {len(timestamps)} unique timestamps. "
                f"Pass an explicit as_of_date or use rank_panel() for multi-period panels."
            )

        eval_ts = pd.to_datetime(as_of_date) if as_of_date else pd.to_datetime(timestamps[0])
        eval_date = eval_ts.date()

        # 1. Fetch active constituents for Point-in-Time Universe safety
        active_symbols: Optional[Set[str]] = None
        if self.universe_manager is not None:
            snap = self.universe_manager.nifty500.get_point_in_time_constituents(eval_date)
            active_symbols = set(snap.symbols)

        # 2. Prepare sector / industry metadata
        sec_map = dict(sector_lookup) if sector_lookup else {}
        ind_map = dict(industry_lookup) if industry_lookup else {}
        if "sector" in df_candidates.columns:
            for _, r in df_candidates[["symbol", "sector"]].dropna().iterrows():
                sec_map.setdefault(str(r["symbol"]).upper().strip(), str(r["sector"]))
        if "industry" in df_candidates.columns:
            for _, r in df_candidates[["symbol", "industry"]].dropna().iterrows():
                ind_map.setdefault(str(r["symbol"]).upper().strip(), str(r["industry"]))
        if self.universe_manager is not None:
            for s in self.universe_manager.nifty500._stocks_by_symbol.values():
                if s.sector:
                    sec_map.setdefault(s.symbol, s.sector)
                if s.industry:
                    ind_map.setdefault(s.symbol, s.industry)

        # 3. Evaluate eligibility for each candidate
        eligible_rows = []
        rejected_items = []

        for _, row in df_candidates.iterrows():
            sym = str(row["symbol"]).upper().strip()
            row_dict = row.to_dict()
            is_eligible, rej_reason = self.filter_engine.evaluate_candidate(
                symbol=sym,
                row_data=row_dict,
                active_universe_symbols=active_symbols,
            )

            if is_eligible:
                row_dict["symbol"] = sym
                row_dict["timestamp"] = eval_ts
                eligible_rows.append(row_dict)
            else:
                rejected_items.append(
                    OpportunityRank(
                        timestamp=eval_ts,
                        symbol=sym,
                        rank=None,
                        opportunity_score=None,
                        is_eligible=False,
                        predicted_return=float(row.get("predicted_return", 0.0)) if pd.notna(row.get("predicted_return")) else None,
                        rejection_reason=rej_reason,
                        scoring_components=None,
                        sector=sec_map.get(sym),
                        industry=ind_map.get(sym),
                    )
                )

        if not eligible_rows:
            return RankedUniverse(
                timestamp=eval_ts,
                ranked_items=rejected_items,
                total_evaluated=len(df_candidates),
                eligible_count=0,
                rejected_count=len(rejected_items),
                top_k=self.config.top_k,
            )

        # 4. Multi-Factor Scoring across eligible stocks
        df_eligible = pd.DataFrame(eligible_rows)
        df_scored = self.scorer.compute_scores(df_eligible)

        # 5. Optional threshold filtering on Opportunity Score
        if self.config.min_opportunity_score is not None:
            below_score_mask = df_scored["opportunity_score"] < self.config.min_opportunity_score
            for _, row in df_scored[below_score_mask].iterrows():
                sym = row["symbol"]
                rejected_items.append(
                    OpportunityRank(
                        timestamp=eval_ts,
                        symbol=sym,
                        rank=None,
                        opportunity_score=float(row["opportunity_score"]),
                        is_eligible=False,
                        predicted_return=float(row["predicted_return"]),
                        rejection_reason=RejectionReason.BELOW_SCORE_THRESHOLD,
                        sector=sec_map.get(sym),
                        industry=ind_map.get(sym),
                    )
                )
            df_scored = df_scored[~below_score_mask].reset_index(drop=True)

        if df_scored.empty:
            return RankedUniverse(
                timestamp=eval_ts,
                ranked_items=rejected_items,
                total_evaluated=len(df_candidates),
                eligible_count=0,
                rejected_count=len(rejected_items),
                top_k=self.config.top_k,
            )

        # 6. Deterministic Tie-Breaking & Sorting
        # 1. opportunity_score descending
        # 2. predicted_return descending
        # 3. symbol ascending (alphabetical)
        df_scored = df_scored.sort_values(
            by=["opportunity_score", "predicted_return", "symbol"],
            ascending=[False, False, True],
        ).reset_index(drop=True)

        # 7. Assign integer ranks (1 ... N)
        ranked_eligible_items = []
        for rank_idx, row in df_scored.iterrows():
            sym = row["symbol"]
            rank_val = rank_idx + 1

            components = ScoringComponents(
                prediction_score=float(row.get("score_prediction", 0.0)),
                risk_adjusted_score=float(row.get("score_risk_adjusted", 0.0)),
                relative_strength_score=float(row.get("score_relative_strength", 0.0)),
                momentum_score=float(row.get("score_momentum", 0.0)),
                trend_score=float(row.get("score_trend", 0.0)),
                regime_score=float(row.get("score_market_regime", 0.0)),
                liquidity_score=float(row.get("score_liquidity", 0.0)),
            )

            ranked_eligible_items.append(
                OpportunityRank(
                    timestamp=eval_ts,
                    symbol=sym,
                    rank=rank_val,
                    opportunity_score=float(row["opportunity_score"]),
                    is_eligible=True,
                    predicted_return=float(row["predicted_return"]),
                    rejection_reason=None,
                    scoring_components=components,
                    sector=sec_map.get(sym),
                    industry=ind_map.get(sym),
                )
            )

        # Combine eligible ranked items and rejected items
        all_items = ranked_eligible_items + rejected_items

        return RankedUniverse(
            timestamp=eval_ts,
            ranked_items=all_items,
            total_evaluated=len(df_candidates),
            eligible_count=len(ranked_eligible_items),
            rejected_count=len(rejected_items),
            top_k=self.config.top_k,
        )

    def rank_panel(
        self,
        df_panel: pd.DataFrame,
        sector_lookup: Optional[Dict[str, str]] = None,
        industry_lookup: Optional[Dict[str, str]] = None,
    ) -> List[RankedUniverse]:
        """
        Rank a multi-period panel across sequential timestamps.
        Each timestamp is ranked strictly independently.
        """
        results = []
        clean = df_panel.copy()
        clean["timestamp"] = pd.to_datetime(clean["timestamp"])
        
        for ts, group in clean.groupby("timestamp", sort=True):
            ranked_uni = self.rank_cross_section(
                df_candidates=group,
                as_of_date=ts,
                sector_lookup=sector_lookup,
                industry_lookup=industry_lookup,
            )
            results.append(ranked_uni)

        return results
