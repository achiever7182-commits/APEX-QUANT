"""
ranking/diagnostics.py — Cross-Sectional Ranking Diagnostics and Multi-Date Walk-Forward Helpers.

Provides:
  1. Return Correlation Matrix Helper: Pairwise correlation computed strictly using data <= t
  2. Single-Snapshot Diagnostics:
     - Spearman Information Coefficient (IC)
     - Score Separation (highest score - lowest score among eligible)
     - Top-Bottom Forward Return Spread (rank 1 return - rank N return)
     - Sector Distribution Diagnostics
  3. Multi-Date Walk-Forward Ranking Diagnostics:
     - Historical multi-timestamp evaluation across candidate panels
     - Aggregate IC statistics: Mean, Median, Standard Deviation, and Hit Rate (IC > 0)
     - Average Score Separation and Average Top-Bottom Forward Return Spread
     - Strict side-by-side benchmark comparison against Raw Prediction, 20d Momentum, and Random baselines
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from ranking.baselines import BaselineRankers
from ranking.models import OpportunityRank, RankedUniverse


@dataclass
class SectorDiagnosticSummary:
    """Summary of ranking characteristics for a single sector."""
    sector: str
    eligible_count: int
    mean_opportunity_score: float
    top_symbol: Optional[str]
    top_score: Optional[float]


@dataclass
class RankingDiagnosticReport:
    """Diagnostic report evaluating the efficacy and distribution of stock rankings at a single snapshot."""
    timestamp: pd.Timestamp
    total_evaluated: int
    eligible_count: int
    score_separation: float
    top_bottom_predicted_spread: float
    spearman_ic: Optional[float] = None
    top_bottom_forward_return_spread: Optional[float] = None
    sector_summaries: Dict[str, SectorDiagnosticSummary] = field(default_factory=dict)

    # Aliases for backward compatibility
    @property
    def top_bottom_score_spread(self) -> float:
        return self.score_separation

    @property
    def realized_top_bottom_spread(self) -> Optional[float]:
        return self.top_bottom_forward_return_spread


@dataclass
class WalkForwardSnapshot:
    """Diagnostic snapshot for a single historical walk-forward evaluation timestamp."""
    timestamp: pd.Timestamp
    sample_count: int
    spearman_ic: Optional[float]
    score_separation: float
    top_bottom_forward_return_spread: Optional[float]
    top_symbol: Optional[str] = None
    bottom_symbol: Optional[str] = None


@dataclass
class WalkForwardRankingReport:
    """
    Aggregate research diagnostics across multi-date historical walk-forward evaluations.
    
    DISCLAIMER: These metrics are empirical research diagnostics for evaluating model
    sorting efficiency. They do not constitute proof of future profitability or production readiness.
    """
    total_dates: int
    ic_mean: float
    ic_median: float
    ic_std: float
    ic_hit_rate: float
    mean_score_separation: float
    mean_top_bottom_forward_return_spread: float
    snapshots: List[WalkForwardSnapshot] = field(default_factory=list)
    baseline_comparison: Dict[str, Dict[str, float]] = field(default_factory=dict)

    def to_dataframe(self) -> pd.DataFrame:
        """Convert individual timestamp snapshots into a structured DataFrame."""
        rows = []
        for s in self.snapshots:
            rows.append({
                "timestamp": s.timestamp,
                "sample_count": s.sample_count,
                "spearman_ic": s.spearman_ic,
                "score_separation": s.score_separation,
                "top_bottom_forward_return_spread": s.top_bottom_forward_return_spread,
                "top_symbol": s.top_symbol,
                "bottom_symbol": s.bottom_symbol,
            })
        return pd.DataFrame(rows)


class RankingDiagnostics:
    """Diagnostic analysis suite for cross-sectional ranking."""

    @staticmethod
    def compute_return_correlation_matrix(
        stock_dfs: Dict[str, pd.DataFrame],
        as_of_date: Union[str, pd.Timestamp],
        lookback_bars: int = 60,
        price_col: str = "close",
        timestamp_col: str = "timestamp",
    ) -> pd.DataFrame:
        """
        Compute historical daily return correlation matrix strictly using data <= as_of_date.

        Zero-lookahead: Observations after as_of_date are strictly filtered out.
        """
        target_dt = pd.to_datetime(as_of_date)
        ts_tz = target_dt.tzinfo

        returns_dict = {}
        for sym, df in stock_dfs.items():
            if df.empty:
                continue
            df_c = df.copy()
            df_c[timestamp_col] = pd.to_datetime(df_c[timestamp_col])
            # Timezone reconciliation
            if ts_tz is not None and df_c[timestamp_col].dt.tz is None:
                df_c[timestamp_col] = df_c[timestamp_col].dt.tz_localize(ts_tz)
            elif ts_tz is None and df_c[timestamp_col].dt.tz is not None:
                df_c[timestamp_col] = df_c[timestamp_col].dt.tz_localize(None)

            # Filter strictly <= as_of_date
            hist_df = df_c[df_c[timestamp_col] <= target_dt].sort_values(timestamp_col)
            if len(hist_df) >= 5:
                tail_df = hist_df.tail(lookback_bars).copy()
                ret = tail_df[price_col].astype(float).pct_change(1)
                returns_dict[sym] = ret.reset_index(drop=True)

        if not returns_dict:
            return pd.DataFrame()

        ret_df = pd.DataFrame(returns_dict)
        return ret_df.corr().fillna(0.0)

    @staticmethod
    def evaluate_ranked_universe(
        ranked_uni: RankedUniverse,
        realized_future_returns: Optional[Dict[str, float]] = None,
    ) -> RankingDiagnosticReport:
        """
        Generate diagnostic metrics for a single RankedUniverse snapshot.

        Parameters:
            ranked_uni: RankedUniverse instance.
            realized_future_returns: Optional mapping of symbol -> realized forward return.
        """
        eligible = ranked_uni.eligible_opportunities
        n_eligible = len(eligible)

        if n_eligible == 0:
            return RankingDiagnosticReport(
                timestamp=ranked_uni.timestamp,
                total_evaluated=ranked_uni.total_evaluated,
                eligible_count=0,
                score_separation=0.0,
                top_bottom_predicted_spread=0.0,
            )

        top_item = eligible[0]
        bottom_item = eligible[-1]

        score_sep = float(top_item.opportunity_score or 0.0) - float(bottom_item.opportunity_score or 0.0)
        pred_spread = float(top_item.predicted_return or 0.0) - float(bottom_item.predicted_return or 0.0)

        # Evaluate realized metrics if outcomes are provided
        spearman_ic = None
        realized_spread = None
        if realized_future_returns:
            scores = []
            realized = []
            for item in eligible:
                if item.symbol in realized_future_returns:
                    scores.append(item.opportunity_score)
                    realized.append(realized_future_returns[item.symbol])

            if len(scores) >= 3 and np.std(scores) > 1e-8 and np.std(realized) > 1e-8:
                corr, _ = spearmanr(scores, realized)
                spearman_ic = float(corr) if not np.isnan(corr) else 0.0

            if top_item.symbol in realized_future_returns and bottom_item.symbol in realized_future_returns:
                realized_spread = (
                    realized_future_returns[top_item.symbol] - realized_future_returns[bottom_item.symbol]
                )

        # Sector Summaries
        sector_groups: Dict[str, List[OpportunityRank]] = {}
        for item in eligible:
            sec = item.sector or "Unclassified"
            sector_groups.setdefault(sec, []).append(item)

        sec_summaries: Dict[str, SectorDiagnosticSummary] = {}
        for sec, items in sector_groups.items():
            scores = [i.opportunity_score for i in items if i.opportunity_score is not None]
            mean_sc = float(np.mean(scores)) if scores else 0.0
            top_i = max(items, key=lambda x: x.opportunity_score or -999.0)
            sec_summaries[sec] = SectorDiagnosticSummary(
                sector=sec,
                eligible_count=len(items),
                mean_opportunity_score=mean_sc,
                top_symbol=top_i.symbol,
                top_score=top_i.opportunity_score,
            )

        return RankingDiagnosticReport(
            timestamp=ranked_uni.timestamp,
            total_evaluated=ranked_uni.total_evaluated,
            eligible_count=n_eligible,
            score_separation=score_sep,
            top_bottom_predicted_spread=pred_spread,
            spearman_ic=spearman_ic,
            top_bottom_forward_return_spread=realized_spread,
            sector_summaries=sec_summaries,
        )

    @classmethod
    def evaluate_historical_walk_forward(
        cls,
        ranker: Any,
        panel_df: pd.DataFrame,
        market_bars: Dict[str, pd.DataFrame],
        forward_horizon_bars: int = 5,
        price_col: str = "close",
        timestamp_col: str = "timestamp",
        symbol_col: str = "symbol",
        min_stocks_per_timestamp: int = 3,
    ) -> WalkForwardRankingReport:
        """
        Evaluate ranking efficacy across multiple historical timestamps (walk-forward).
        
        For each date t:
          1. Evaluates candidate slice strictly at date t.
          2. Computes forward returns from date t to t + forward_horizon_bars.
          3. Evaluates Spearman IC, Score Separation, and Top-Bottom Forward Return Spread.
          4. Compares against reference baselines (Raw Prediction, 20d Momentum, Random).
        """
        df_clean = panel_df.copy()
        df_clean[timestamp_col] = pd.to_datetime(df_clean[timestamp_col])
        unique_dates = sorted(df_clean[timestamp_col].unique())

        snapshots: List[WalkForwardSnapshot] = []
        ic_list: List[float] = []
        sep_list: List[float] = []
        spread_list: List[float] = []

        # Baseline trackers
        baseline_ics: Dict[str, List[float]] = {
            "Raw Prediction": [],
            "20d Momentum": [],
            "Random": [],
        }
        baseline_spreads: Dict[str, List[float]] = {
            "Raw Prediction": [],
            "20d Momentum": [],
            "Random": [],
        }

        for ts in unique_dates:
            slice_df = df_clean[df_clean[timestamp_col] == ts]
            if len(slice_df) < min_stocks_per_timestamp:
                continue

            # Realized forward returns for available stocks
            fwd_returns: Dict[str, float] = {}
            for _, r in slice_df.iterrows():
                sym = str(r[symbol_col]).upper().strip()
                if sym in market_bars:
                    b_df = market_bars[sym].copy()
                    b_df[timestamp_col] = pd.to_datetime(b_df[timestamp_col])
                    matches = b_df[b_df[timestamp_col].dt.date == pd.to_datetime(ts).date()].index
                    if len(matches) > 0:
                        loc = matches[0]
                        if loc + forward_horizon_bars < len(b_df):
                            p0 = float(b_df.iloc[loc][price_col])
                            p1 = float(b_df.iloc[loc + forward_horizon_bars][price_col])
                            if p0 > 0:
                                fwd_returns[sym] = (p1 / p0) - 1.0

            if len(fwd_returns) < min_stocks_per_timestamp:
                continue

            # 1. Apex Composite Ranking
            ranked_uni = ranker.rank_cross_section(slice_df, as_of_date=ts)
            rep = cls.evaluate_ranked_universe(ranked_uni, realized_future_returns=fwd_returns)

            top_sym = ranked_uni.eligible_opportunities[0].symbol if ranked_uni.eligible_count > 0 else None
            bottom_sym = ranked_uni.eligible_opportunities[-1].symbol if ranked_uni.eligible_count > 0 else None

            snap = WalkForwardSnapshot(
                timestamp=pd.to_datetime(ts),
                sample_count=rep.eligible_count,
                spearman_ic=rep.spearman_ic,
                score_separation=rep.score_separation,
                top_bottom_forward_return_spread=rep.top_bottom_forward_return_spread,
                top_symbol=top_sym,
                bottom_symbol=bottom_sym,
            )
            snapshots.append(snap)

            if rep.spearman_ic is not None:
                ic_list.append(rep.spearman_ic)
            sep_list.append(rep.score_separation)
            if rep.top_bottom_forward_return_spread is not None:
                spread_list.append(rep.top_bottom_forward_return_spread)

            # 2. Baseline evaluations on identical timestamp slice
            # Raw Prediction
            raw_r = BaselineRankers.rank_by_raw_prediction(slice_df)
            raw_rep = cls.evaluate_ranked_universe(raw_r, realized_future_returns=fwd_returns)
            if raw_rep.spearman_ic is not None:
                baseline_ics["Raw Prediction"].append(raw_rep.spearman_ic)
            if raw_rep.top_bottom_forward_return_spread is not None:
                baseline_spreads["Raw Prediction"].append(raw_rep.top_bottom_forward_return_spread)

            # 20d Momentum
            mom_col = "roc_20d" if "roc_20d" in slice_df.columns else ("momentum_norm_20d" if "momentum_norm_20d" in slice_df.columns else None)
            if mom_col:
                mom_r = BaselineRankers.rank_by_momentum(slice_df, mom_col=mom_col)
                mom_rep = cls.evaluate_ranked_universe(mom_r, realized_future_returns=fwd_returns)
                if mom_rep.spearman_ic is not None:
                    baseline_ics["20d Momentum"].append(mom_rep.spearman_ic)
                if mom_rep.top_bottom_forward_return_spread is not None:
                    baseline_spreads["20d Momentum"].append(mom_rep.top_bottom_forward_return_spread)

            # Random
            rnd_r = BaselineRankers.rank_random(slice_df, random_seed=int(pd.to_datetime(ts).timestamp()) % 10000)
            rnd_rep = cls.evaluate_ranked_universe(rnd_r, realized_future_returns=fwd_returns)
            if rnd_rep.spearman_ic is not None:
                baseline_ics["Random"].append(rnd_rep.spearman_ic)
            if rnd_rep.top_bottom_forward_return_spread is not None:
                baseline_spreads["Random"].append(rnd_rep.top_bottom_forward_return_spread)

        total_d = len(snapshots)
        ic_arr = np.array(ic_list) if ic_list else np.array([0.0])
        hit_count = int(np.sum(ic_arr > 0))
        hit_rate = float(hit_count / len(ic_arr)) if len(ic_arr) > 0 else 0.0

        # Compile baseline comparison
        comp_summary: Dict[str, Dict[str, float]] = {
            "Apex Composite": {
                "mean_ic": float(np.mean(ic_arr)),
                "median_ic": float(np.median(ic_arr)),
                "std_ic": float(np.std(ic_arr)),
                "ic_hit_rate": hit_rate,
                "mean_forward_return_spread": float(np.mean(spread_list)) if spread_list else 0.0,
            }
        }
        for b_name in ("Raw Prediction", "20d Momentum", "Random"):
            b_ics = np.array(baseline_ics[b_name]) if baseline_ics[b_name] else np.array([0.0])
            b_spreads = baseline_spreads[b_name]
            comp_summary[b_name] = {
                "mean_ic": float(np.mean(b_ics)),
                "median_ic": float(np.median(b_ics)),
                "std_ic": float(np.std(b_ics)),
                "ic_hit_rate": float(np.sum(b_ics > 0) / len(b_ics)) if len(b_ics) > 0 else 0.0,
                "mean_forward_return_spread": float(np.mean(b_spreads)) if b_spreads else 0.0,
            }

        return WalkForwardRankingReport(
            total_dates=total_d,
            ic_mean=float(np.mean(ic_arr)),
            ic_median=float(np.median(ic_arr)),
            ic_std=float(np.std(ic_arr)),
            ic_hit_rate=hit_rate,
            mean_score_separation=float(np.mean(sep_list)) if sep_list else 0.0,
            mean_top_bottom_forward_return_spread=float(np.mean(spread_list)) if spread_list else 0.0,
            snapshots=snapshots,
            baseline_comparison=comp_summary,
        )
