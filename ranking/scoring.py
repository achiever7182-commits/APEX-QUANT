"""
ranking/scoring.py — Multi-Factor Cross-Sectional Opportunity Scoring.

Computes:
  1. Prediction Score: Cross-sectionally normalized predicted return
  2. Risk-Adjusted Score: Predicted return divided by volatility, normalized cross-sectionally
  3. Relative Strength Score: Cross-sectional excess return vs benchmark
  4. Momentum Score: Cross-sectional blend of RSI, ROC, and price momentum
  5. Trend Score: Price-to-SMA ratio and moving average spread
  6. Market Regime Score: Macro state (+1 Bullish -> 1.0, 0 Neutral -> 0.5, -1 Bearish -> 0.0)
  7. Liquidity Score: Normalized turnover consistency
  8. Composite Opportunity Score: Configurable weighted linear combination

STRICT ZERO-LOOKAHEAD INVARIANT:
  All transformations are computed strictly across the cross-section of eligible stocks
  at the single evaluation timestamp t. Future dates never contaminate date t.
"""

from __future__ import annotations

from typing import Dict, List, Optional
import numpy as np
import pandas as pd

from ranking.config import RankingConfig
from ranking.models import ScoringComponents


class OpportunityScorer:
    """Computes normalized factor sub-scores and composite opportunity scores."""

    def __init__(self, config: Optional[RankingConfig] = None):
        self.config = config or RankingConfig()

    def _normalize_series(self, s: pd.Series, ascending: bool = True) -> pd.Series:
        """
        Normalize a cross-sectional series according to config.
        Default: Percentile Rank uniformly distributed in [0.0, 1.0].
        """
        valid = s.dropna()
        neutral_val = 0.5 if self.config.normalization_method == "percentile" else 0.0
        if len(valid) <= 1:
            return pd.Series(neutral_val, index=s.index)

        if self.config.normalization_method == "percentile":
            # rank(pct=True) returns (1/N ... 1.0). Scale to [0.0, 1.0]
            ranks = s.rank(ascending=ascending, method="average", pct=True)
            return ranks.fillna(0.5)
        elif self.config.normalization_method == "zscore":
            std = float(s.std())
            if std > 1e-8:
                z = (s - float(s.mean())) / std
                return z.fillna(0.0)
            return pd.Series(0.0, index=s.index)
        else:
            return s.fillna(neutral_val)

    def compute_scores(self, df_eligible: pd.DataFrame) -> pd.DataFrame:
        """
        Compute factor scores for all eligible stocks at a single timestamp.

        Parameters:
            df_eligible: DataFrame containing eligible stocks with predictions and features.

        Returns:
            DataFrame with added columns for each sub-score and 'opportunity_score'.
        """
        out = df_eligible.copy()
        if out.empty:
            out["opportunity_score"] = pd.Series(dtype=float)
            return out

        neutral_val = 0.5 if self.config.normalization_method == "percentile" else 0.0

        # 1. Prediction Score
        preds = out["predicted_return"].astype(float)
        out["score_prediction"] = self._normalize_series(preds, ascending=True)

        # 2. Risk-Adjusted Score: Return / (volatility + epsilon)
        vol_col = "volatility_20d" if "volatility_20d" in out.columns else "volatility_10d"
        if vol_col in out.columns:
            vols = out[vol_col].astype(float).clip(lower=1e-4).fillna(0.02)
            # Safe risk-adjusted ratio
            risk_adj = preds / (vols + 1e-6)
            # Clip extreme ratios
            risk_adj = risk_adj.clip(lower=-50.0, upper=50.0)
            out["score_risk_adjusted"] = self._normalize_series(risk_adj, ascending=True)
        else:
            out["score_risk_adjusted"] = out["score_prediction"]

        # 3. Relative Strength Score: 20d or 60d relative return vs benchmark
        if "relative_return_20d" in out.columns:
            rel_ret = out["relative_return_20d"].astype(float).fillna(0.0)
            out["score_relative_strength"] = self._normalize_series(rel_ret, ascending=True)
        elif "relative_return_5d" in out.columns:
            rel_ret = out["relative_return_5d"].astype(float).fillna(0.0)
            out["score_relative_strength"] = self._normalize_series(rel_ret, ascending=True)
        else:
            out["score_relative_strength"] = neutral_val

        # 4. Momentum Score: blend of RSI, ROC 20d, and normalized momentum
        mom_components = []
        if "rsi_14" in out.columns:
            mom_components.append(self._normalize_series(out["rsi_14"].astype(float).fillna(50.0)))
        if "roc_20d" in out.columns:
            mom_components.append(self._normalize_series(out["roc_20d"].astype(float).fillna(0.0)))
        if "momentum_norm_20d" in out.columns:
            mom_components.append(self._normalize_series(out["momentum_norm_20d"].astype(float).fillna(0.0)))

        if mom_components:
            out["score_momentum"] = pd.concat(mom_components, axis=1).mean(axis=1)
        else:
            out["score_momentum"] = neutral_val

        # 5. Trend Score: price_to_sma_20_ratio and sma_20_to_50_spread
        trend_components = []
        if "price_to_sma_20_ratio" in out.columns:
            trend_components.append(self._normalize_series(out["price_to_sma_20_ratio"].astype(float).fillna(0.0)))
        if "sma_20_to_50_spread" in out.columns:
            trend_components.append(self._normalize_series(out["sma_20_to_50_spread"].astype(float).fillna(0.0)))

        if trend_components:
            out["score_trend"] = pd.concat(trend_components, axis=1).mean(axis=1)
        else:
            out["score_trend"] = neutral_val

        # 6. Market Regime Score: Map regime_market_state
        if "regime_market_state" in out.columns:
            reg_val = out["regime_market_state"].astype(float).fillna(0.0)
            if self.config.normalization_method == "percentile":
                out["score_market_regime"] = np.where(reg_val > 0, 1.0, np.where(reg_val < 0, 0.0, 0.5))
            else:
                out["score_market_regime"] = self._normalize_series(reg_val)
        else:
            out["score_market_regime"] = neutral_val

        # 7. Liquidity Score: Normalized turnover
        if "turnover_sma_20d" in out.columns:
            out["score_liquidity"] = self._normalize_series(out["turnover_sma_20d"].astype(float).fillna(0.0))
        elif "turnover" in out.columns:
            out["score_liquidity"] = self._normalize_series(out["turnover"].astype(float).fillna(0.0))
        else:
            out["score_liquidity"] = neutral_val

        # 8. Composite Opportunity Score (Weighted Linear Combination)
        w = self.config.weights
        opp_score = (
            w.get("prediction", 0.35) * out["score_prediction"]
            + w.get("risk_adjusted", 0.20) * out["score_risk_adjusted"]
            + w.get("relative_strength", 0.15) * out["score_relative_strength"]
            + w.get("momentum", 0.10) * out["score_momentum"]
            + w.get("trend", 0.10) * out["score_trend"]
            + w.get("market_regime", 0.05) * out["score_market_regime"]
            + w.get("liquidity", 0.05) * out["score_liquidity"]
        )

        if self.config.normalization_method == "zscore":
            out["opportunity_score"] = self._normalize_series(opp_score)
        else:
            out["opportunity_score"] = opp_score

        return out
