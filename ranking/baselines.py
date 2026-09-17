"""
ranking/baselines.py — Baseline Ranking Strategies for Comparative Benchmarking.

Implements standard benchmark rankers:
  1. Raw Prediction Ranker: Ranks purely by predicted_return descending
  2. Momentum Ranker: Ranks purely by 20-day momentum (ROC 20d) descending
  3. Random Ranker: Deterministic pseudo-random permutation for null hypothesis testing
"""

from __future__ import annotations

from typing import Optional, Union
import numpy as np
import pandas as pd

from ranking.models import OpportunityRank, RankedUniverse


class BaselineRankers:
    """Provides non-composite reference rankings for sanity checking and research comparison."""

    @staticmethod
    def rank_by_raw_prediction(
        df_candidates: pd.DataFrame,
        as_of_date: Optional[Union[str, pd.Timestamp]] = None,
        pred_col: str = "predicted_return",
    ) -> RankedUniverse:
        """Rank eligible stocks strictly by predicted return descending."""
        eval_ts = pd.to_datetime(as_of_date) if as_of_date else pd.Timestamp.now()
        if df_candidates.empty:
            return RankedUniverse(timestamp=eval_ts, ranked_items=[], total_evaluated=0, eligible_count=0, rejected_count=0)

        clean = df_candidates.copy()
        clean = clean[clean[pred_col].notna()].reset_index(drop=True)

        # Sort: 1. predicted_return desc, 2. symbol asc
        clean = clean.sort_values(by=[pred_col, "symbol"], ascending=[False, True]).reset_index(drop=True)

        ranked_items = []
        for rank_idx, row in clean.iterrows():
            sym = str(row["symbol"]).upper().strip()
            ranked_items.append(
                OpportunityRank(
                    timestamp=eval_ts,
                    symbol=sym,
                    rank=rank_idx + 1,
                    opportunity_score=float(row[pred_col]),
                    is_eligible=True,
                    predicted_return=float(row[pred_col]),
                    sector=row.get("sector"),
                    industry=row.get("industry"),
                )
            )

        return RankedUniverse(
            timestamp=eval_ts,
            ranked_items=ranked_items,
            total_evaluated=len(df_candidates),
            eligible_count=len(ranked_items),
            rejected_count=len(df_candidates) - len(ranked_items),
        )

    @staticmethod
    def rank_by_momentum(
        df_candidates: pd.DataFrame,
        as_of_date: Optional[Union[str, pd.Timestamp]] = None,
        mom_col: str = "roc_20d",
    ) -> RankedUniverse:
        """Rank stocks strictly by 20-day momentum (Rate of Change) descending."""
        eval_ts = pd.to_datetime(as_of_date) if as_of_date else pd.Timestamp.now()
        if df_candidates.empty:
            return RankedUniverse(timestamp=eval_ts, ranked_items=[], total_evaluated=0, eligible_count=0, rejected_count=0)

        clean = df_candidates.copy()
        # Fallback to return_20d if roc_20d is absent
        target_mom_col = mom_col if mom_col in clean.columns else "return_20d"
        clean = clean[clean[target_mom_col].notna()].reset_index(drop=True)

        clean = clean.sort_values(by=[target_mom_col, "symbol"], ascending=[False, True]).reset_index(drop=True)

        ranked_items = []
        for rank_idx, row in clean.iterrows():
            sym = str(row["symbol"]).upper().strip()
            ranked_items.append(
                OpportunityRank(
                    timestamp=eval_ts,
                    symbol=sym,
                    rank=rank_idx + 1,
                    opportunity_score=float(row[target_mom_col]),
                    is_eligible=True,
                    predicted_return=float(row.get("predicted_return", 0.0)) if pd.notna(row.get("predicted_return")) else None,
                    sector=row.get("sector"),
                    industry=row.get("industry"),
                )
            )

        return RankedUniverse(
            timestamp=eval_ts,
            ranked_items=ranked_items,
            total_evaluated=len(df_candidates),
            eligible_count=len(ranked_items),
            rejected_count=len(df_candidates) - len(ranked_items),
        )

    @staticmethod
    def rank_random(
        df_candidates: pd.DataFrame,
        random_seed: int = 42,
        as_of_date: Optional[Union[str, pd.Timestamp]] = None,
    ) -> RankedUniverse:
        """Deterministic pseudo-random permutation baseline."""
        eval_ts = pd.to_datetime(as_of_date) if as_of_date else pd.Timestamp.now()
        if df_candidates.empty:
            return RankedUniverse(timestamp=eval_ts, ranked_items=[], total_evaluated=0, eligible_count=0, rejected_count=0)

        rng = np.random.RandomState(random_seed)
        shuffled = df_candidates.sample(frac=1.0, random_state=rng).reset_index(drop=True)

        ranked_items = []
        for rank_idx, row in shuffled.iterrows():
            sym = str(row["symbol"]).upper().strip()
            ranked_items.append(
                OpportunityRank(
                    timestamp=eval_ts,
                    symbol=sym,
                    rank=rank_idx + 1,
                    opportunity_score=1.0 - (rank_idx / len(shuffled)),
                    is_eligible=True,
                    predicted_return=float(row.get("predicted_return", 0.0)) if pd.notna(row.get("predicted_return")) else None,
                    sector=row.get("sector"),
                    industry=row.get("industry"),
                )
            )

        return RankedUniverse(
            timestamp=eval_ts,
            ranked_items=ranked_items,
            total_evaluated=len(df_candidates),
            eligible_count=len(ranked_items),
            rejected_count=0,
        )
