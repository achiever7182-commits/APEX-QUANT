"""
ml/equity/evaluate.py — Comprehensive Regression and Cross-Sectional Diagnostics.

Computes:
  1. Standard Regression Metrics:
     - MAE, RMSE, R²
     - Pearson correlation between predicted and actual returns
     - Directional Accuracy: % of predictions matching realized sign
  2. Cross-Sectional Diagnostics (Vital for Future Stock Ranking):
     - Information Coefficient (IC): Daily Spearman rank correlation across stocks
     - IC Mean, IC Standard Deviation, IC Information Ratio (IC_IR = Mean / Std)
     - % Positive IC trading days
     - Quantile return spread: realized returns grouped by prediction buckets (e.g. top vs bottom)
  3. Baseline Comparison:
     - Direct side-by-side comparison of candidate model vs naive benchmark

NO CAUSAL OR PROFITABILITY CLAIMS:
  These metrics measure statistical association and cross-sectional rank ordering only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score


@dataclass
class RegressionMetrics:
    """Standard point-forecast performance metrics."""
    mae: float
    rmse: float
    r2: float
    directional_accuracy: float
    pearson_corr: float
    mean_predicted: float
    mean_actual: float
    total_samples: int


@dataclass
class CrossSectionalMetrics:
    """Cross-sectional rank metrics across instruments at identical timestamps."""
    mean_ic: float
    std_ic: float
    ic_ir: float
    pct_positive_ic: float
    daily_ics: Dict[str, float] = field(default_factory=dict)
    bucket_realized_returns: Dict[str, float] = field(default_factory=dict)
    top_minus_bottom_spread: float = 0.0
    evaluated_dates_count: int = 0


@dataclass
class ModelEvaluationReport:
    """Complete diagnostic report combining time-series and cross-sectional performance."""
    model_name: str
    target_name: str
    regression_metrics: RegressionMetrics
    cross_sectional_metrics: CrossSectionalMetrics
    baseline_comparison: Dict[str, Any] = field(default_factory=dict)


class EquityEvaluator:
    """Evaluates equity predictions across time and across instruments."""

    @staticmethod
    def calculate_regression_metrics(
        y_true: np.ndarray,
        y_pred: np.ndarray,
    ) -> RegressionMetrics:
        """Calculate point forecast metrics."""
        mask = (~np.isnan(y_true)) & (~np.isnan(y_pred))
        yt = y_true[mask]
        yp = y_pred[mask]

        if len(yt) < 2:
            return RegressionMetrics(
                mae=0.0, rmse=0.0, r2=0.0, directional_accuracy=0.0,
                pearson_corr=0.0, mean_predicted=0.0, mean_actual=0.0, total_samples=len(yt),
            )

        mae = float(mean_absolute_error(yt, yp))
        rmse = float(np.sqrt(mean_squared_error(yt, yp)))
        r2 = float(r2_score(yt, yp))

        # Directional accuracy: sign(y_pred) == sign(y_true)
        sign_match = (np.sign(yp) == np.sign(yt)).astype(float)
        dir_acc = float(np.mean(sign_match))

        # Pearson correlation
        std_p = np.std(yp)
        std_t = np.std(yt)
        if std_p > 1e-12 and std_t > 1e-12:
            p_corr = float(np.corrcoef(yp, yt)[0, 1])
        else:
            p_corr = 0.0

        return RegressionMetrics(
            mae=mae,
            rmse=rmse,
            r2=r2,
            directional_accuracy=dir_acc,
            pearson_corr=p_corr,
            mean_predicted=float(np.mean(yp)),
            mean_actual=float(np.mean(yt)),
            total_samples=len(yt),
        )

    @staticmethod
    def calculate_cross_sectional_metrics(
        df: pd.DataFrame,
        pred_col: str = "pred",
        target_col: str = "target",
        timestamp_col: str = "timestamp",
        symbol_col: str = "symbol",
        n_buckets: int = 5,
    ) -> CrossSectionalMetrics:
        """
        Evaluate daily Spearman rank correlation (IC) and quantile return buckets across stocks.
        """
        clean = df[[timestamp_col, symbol_col, pred_col, target_col]].dropna().copy()
        clean[timestamp_col] = pd.to_datetime(clean[timestamp_col])

        daily_ics: Dict[str, float] = {}
        # 1. Daily Spearman Rank Correlation
        for ts, group in clean.groupby(timestamp_col):
            if len(group) < 3:
                # Need at least 3 stocks to compute meaningful rank correlation
                continue
            
            p = group[pred_col].values
            y = group[target_col].values
            
            # Avoid nan in spearmanr when std is 0
            if np.std(p) > 1e-12 and np.std(y) > 1e-12:
                corr, _ = spearmanr(p, y)
                if not np.isnan(corr):
                    daily_ics[str(ts.date())] = float(corr)

        ic_values = list(daily_ics.values())
        if ic_values:
            mean_ic = float(np.mean(ic_values))
            std_ic = float(np.std(ic_values))
            ic_ir = float(mean_ic / (std_ic + 1e-9))
            pct_pos = float(np.mean([1.0 if x > 0 else 0.0 for x in ic_values])) * 100.0
        else:
            mean_ic, std_ic, ic_ir, pct_pos = 0.0, 0.0, 0.0, 0.0

        # 2. Prediction Bucket Analysis (Quantiles / Buckets)
        # Slices predictions into n_buckets per timestamp, and measures realized future return
        bucket_returns: Dict[str, List[float]] = {f"Q{i+1}": [] for i in range(n_buckets)}

        for _, group in clean.groupby(timestamp_col):
            if len(group) < n_buckets:
                continue
            # Rank predictions from 0 to 1
            ranks = group[pred_col].rank(pct=True, method="first")
            for i in range(n_buckets):
                lower_q = i / n_buckets
                upper_q = (i + 1) / n_buckets
                mask = (ranks > lower_q) & (ranks <= upper_q)
                sub = group.loc[mask, target_col]
                if not sub.empty:
                    bucket_returns[f"Q{i+1}"].append(float(sub.mean()))

        bucket_means: Dict[str, float] = {}
        for b_name, rets in bucket_returns.items():
            bucket_means[b_name] = float(np.mean(rets)) if rets else 0.0

        q_top = bucket_means.get(f"Q{n_buckets}", 0.0)
        q_bot = bucket_means.get("Q1", 0.0)
        spread = q_top - q_bot

        return CrossSectionalMetrics(
            mean_ic=mean_ic,
            std_ic=std_ic,
            ic_ir=ic_ir,
            pct_positive_ic=pct_pos,
            daily_ics=daily_ics,
            bucket_realized_returns=bucket_means,
            top_minus_bottom_spread=spread,
            evaluated_dates_count=len(daily_ics),
        )

    @classmethod
    def evaluate_model(
        cls,
        model_name: str,
        target_name: str,
        eval_df: pd.DataFrame,
        pred_col: str = "pred",
        target_col: str = "target",
        naive_pred_col: Optional[str] = None,
    ) -> ModelEvaluationReport:
        """Generate full evaluation report for an equity forecasting model."""
        y_true = eval_df[target_col].values
        y_pred = eval_df[pred_col].values

        reg_metrics = cls.calculate_regression_metrics(y_true, y_pred)
        cs_metrics = cls.calculate_cross_sectional_metrics(eval_df, pred_col=pred_col, target_col=target_col)

        baseline_comp = {}
        if naive_pred_col and naive_pred_col in eval_df.columns:
            naive_pred = eval_df[naive_pred_col].values
            naive_reg = cls.calculate_regression_metrics(y_true, naive_pred)
            baseline_comp = {
                "naive_mae": naive_reg.mae,
                "naive_rmse": naive_reg.rmse,
                "mae_improvement_pct": ((naive_reg.mae - reg_metrics.mae) / (naive_reg.mae + 1e-12)) * 100.0,
                "rmse_improvement_pct": ((naive_reg.rmse - reg_metrics.rmse) / (naive_reg.rmse + 1e-12)) * 100.0,
            }

        return ModelEvaluationReport(
            model_name=model_name,
            target_name=target_name,
            regression_metrics=reg_metrics,
            cross_sectional_metrics=cs_metrics,
            baseline_comparison=baseline_comp,
        )
