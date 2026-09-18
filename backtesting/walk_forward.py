"""
backtesting/walk_forward.py — Walk-forward period partitioning and model retraining interface.

Supports expanding-window historical model training policies (data < T) and
chronological sub-period performance breakdown to test regime robustness.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional
import numpy as np
import pandas as pd

from backtesting.models import PortfolioSnapshot, WalkForwardPeriodResult


class WalkForwardAnalyzer:
    """
    Partitions simulation history into chronological sub-periods and audits performance stability.
    """

    @staticmethod
    def partition_snapshots_by_period(
        snapshots: List[PortfolioSnapshot],
        period_freq: str = "QE",  # 'QE' for Quarter End, '6ME' for Semi-Annual, 'YE' for Annual
    ) -> List[WalkForwardPeriodResult]:
        """
        Segment daily snapshots into sequential sub-periods and calculate period statistics.
        """
        if not snapshots or len(snapshots) < 5:
            return []

        # Reconcile pandas 2.2+ offset aliases
        freq_alias = period_freq
        if freq_alias == "Q":
            freq_alias = "QE"
        elif freq_alias == "M":
            freq_alias = "ME"
        elif freq_alias == "Y":
            freq_alias = "YE"

        df_snaps = pd.DataFrame([
            {
                "timestamp": s.timestamp,
                "portfolio_value": s.portfolio_value,
                "daily_return": s.daily_return,
                "drawdown": s.drawdown,
                "fees": s.fees_paid,
                "slippage": s.slippage_paid,
                "turnover": s.turnover,
            }
            for s in snapshots
        ])
        df_snaps["timestamp"] = pd.to_datetime(df_snaps["timestamp"])
        df_snaps = df_snaps.sort_values("timestamp").reset_index(drop=True)

        # Group by specified calendar period
        periods: List[WalkForwardPeriodResult] = []
        try:
            grouper = pd.Grouper(key="timestamp", freq=freq_alias)
        except Exception:
            grouper = pd.Grouper(key="timestamp", freq="QE")

        for p_key, group in df_snaps.groupby(grouper):
            if group.empty or len(group) < 2:
                continue

            start_dt = group.iloc[0]["timestamp"].strftime("%Y-%m-%d")
            end_dt = group.iloc[-1]["timestamp"].strftime("%Y-%m-%d")
            p_id = f"{start_dt} to {end_dt}"

            p_start_val = group.iloc[0]["portfolio_value"]
            p_end_val = group.iloc[-1]["portfolio_value"]
            p_return = (p_end_val - p_start_val) / p_start_val if p_start_val > 0 else 0.0

            rets = group["daily_return"].values[1:] if len(group) > 1 else np.array([0.0])
            ann_vol = np.std(rets) * np.sqrt(252.0) if len(rets) > 1 else 0.0
            ann_ret = np.mean(rets) * 252.0 if len(rets) > 0 else 0.0
            sharpe = (ann_ret / ann_vol) if ann_vol > 1e-6 else 0.0
            max_dd = float(group["drawdown"].max()) if not group["drawdown"].empty else 0.0

            p_turnover = float(group["turnover"].sum())
            p_fees = float(group.iloc[-1]["fees"] - group.iloc[0]["fees"])
            p_slip = float(group.iloc[-1]["slippage"] - group.iloc[0]["slippage"])

            periods.append(WalkForwardPeriodResult(
                period_id=p_id,
                start_date=start_dt,
                end_date=end_dt,
                total_return=p_return,
                annualized_volatility=ann_vol,
                sharpe_ratio=sharpe,
                max_drawdown=max_dd,
                turnover=p_turnover,
                total_costs=p_fees + p_slip,
            ))

        return periods


@dataclass
class WalkForwardTrainAuditLog:
    """Detailed diagnostic log for each point-in-time walk-forward ML training event."""
    prediction_date: str
    training_start: str
    training_end: str
    sample_count: int
    model_name: str
    feature_count: int
    train_mae: float
    train_ic: float


class WalkForwardMLTrainer:
    """
    Genuine Point-in-Time Expanding-Window ML Trainer for APEX-QUANT.

    Guarantees:
      1. For every prediction date T:
         - Training data contains ONLY observations whose target horizon is fully observed at or before T.
           i.e. observation timestamp t satisfies: t + horizon <= T (strictly t <= T - horizon).
         - Features for each observation t are constructed strictly from data <= t.
         - Target for observation t is Close_{t+k} / Close_t - 1.0.
         - Preprocessors (Imputer, Scaler) are fitted strictly on the point-in-time training window.
         - No future data can ever enter model training or feature normalization.
      2. Zero look-ahead bias:
         - training_end < prediction_date is strictly enforced.
         - Predictions for date T cross-section use only features <= T.
      3. Deterministic execution with fixed random seed.
      4. Detailed audit logging of every training event.
    """

    def __init__(
        self,
        model_type: str = "ridge",
        target_horizon: int = 5,
        min_train_samples: int = 100,
        random_state: int = 42,
    ) -> None:
        self.model_type = model_type.lower()
        self.target_horizon = target_horizon
        self.min_train_samples = min_train_samples
        self.random_state = random_state
        self.audit_logs: List[WalkForwardTrainAuditLog] = []

    def train_and_predict(
        self,
        candidate_panel: pd.DataFrame,
        as_of_time: pd.Timestamp,
    ) -> pd.DataFrame:
        """
        Train expanding-window model on historical data <= as_of_time and predict cross-section at as_of_time.

        Parameters:
            candidate_panel: Full cross-sectional DataFrame with features and prices.
            as_of_time: Current simulation timestamp T.

        Returns:
            Cross-sectional DataFrame for as_of_time with added 'predicted_return' column.
        """
        panel_df = candidate_panel.copy()
        panel_df["timestamp"] = pd.to_datetime(panel_df["timestamp"])

        # 1. Strict point-in-time historical data slice <= as_of_time
        if as_of_time.tzinfo is not None and panel_df["timestamp"].dt.tz is None:
            tz_as_of = as_of_time.tz_localize(None)
            hist_panel = panel_df[panel_df["timestamp"] <= tz_as_of].copy()
            slice_today = panel_df[panel_df["timestamp"].dt.date == tz_as_of.date()].copy()
        elif as_of_time.tzinfo is None and panel_df["timestamp"].dt.tz is not None:
            hist_panel = panel_df[panel_df["timestamp"].dt.tz_localize(None) <= as_of_time].copy()
            slice_today = panel_df[panel_df["timestamp"].dt.tz_localize(None).dt.date == as_of_time.date()].copy()
        else:
            hist_panel = panel_df[panel_df["timestamp"] <= as_of_time].copy()
            slice_today = panel_df[panel_df["timestamp"].dt.date == as_of_time.date()].copy()

        if slice_today.empty:
            return slice_today

        # Identify feature columns (all numeric columns excluding identifiers, target, and predictions)
        exclude_cols = {
            "timestamp", "symbol", "close", "target_return_5d", "predicted_return",
            "sector", "industry", "is_eligible", "rejection_reason", "target", "date"
        }
        feature_cols = [
            c for c in hist_panel.columns
            if c not in exclude_cols and pd.api.types.is_numeric_dtype(hist_panel[c])
        ]

        # 2. Compute Point-in-Time Forward Target strictly within hist_panel
        # By shifting backwards by -k within hist_panel (which has data <= as_of_time),
        # only observations where t + k <= as_of_time will receive a non-NaN target.
        # Observations whose target occurs AFTER as_of_time automatically receive NaN!
        hist_panel = hist_panel.sort_values(["symbol", "timestamp"]).reset_index(drop=True)
        future_close = hist_panel.groupby("symbol")["close"].shift(-self.target_horizon)
        hist_panel["_pit_target"] = (future_close / hist_panel["close"]) - 1.0

        # 3. Filter to valid training observations (must have valid target and non-null features)
        train_mask = hist_panel["_pit_target"].notna()
        train_df = hist_panel[train_mask].copy()

        # Audit Check: Verify training_end < as_of_time
        as_of_date_str = as_of_time.strftime("%Y-%m-%d")
        if not train_df.empty:
            training_start_dt = train_df["timestamp"].min()
            training_end_dt = train_df["timestamp"].max()
            training_start_str = training_start_dt.strftime("%Y-%m-%d")
            training_end_str = training_end_dt.strftime("%Y-%m-%d")
            assert training_end_dt < as_of_time, (
                f"LOOK-AHEAD LEAK: training_end ({training_end_str}) must be strictly < prediction_date ({as_of_date_str})"
            )
        else:
            training_start_str = "N/A"
            training_end_str = "N/A"

        # 4. Model Training or Baseline Fallback
        if len(train_df) < self.min_train_samples:
            # Insufficient samples: Predict zero return baseline
            slice_today["predicted_return"] = 0.0
            self.audit_logs.append(WalkForwardTrainAuditLog(
                prediction_date=as_of_date_str,
                training_start=training_start_str,
                training_end=training_end_str,
                sample_count=len(train_df),
                model_name="Fallback_Zero",
                feature_count=len(feature_cols),
                train_mae=0.0,
                train_ic=0.0,
            ))
            return slice_today

        X_train = train_df[feature_cols]
        y_train = train_df["_pit_target"]
        X_today = slice_today[feature_cols]

        # Construct strictly isolated pipeline
        from sklearn.impute import SimpleImputer
        from sklearn.preprocessing import StandardScaler
        from sklearn.linear_model import Ridge
        from sklearn.ensemble import RandomForestRegressor
        from sklearn.pipeline import Pipeline
        from scipy.stats import spearmanr

        if self.model_type == "random_forest":
            model = RandomForestRegressor(
                n_estimators=50,
                max_depth=5,
                min_samples_leaf=10,
                random_state=self.random_state,
                n_jobs=-1,
            )
            pipe = Pipeline([
                ("imputer", SimpleImputer(strategy="median")),
                ("regressor", model),
            ])
            model_label = "RandomForest(n=50,depth=5)"
        else:
            # Default: L2 Ridge regression with training-only scaling
            model = Ridge(alpha=10.0, random_state=self.random_state)
            pipe = Pipeline([
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
                ("regressor", model),
            ])
            model_label = "Ridge(alpha=10.0)"

        # Fit preprocessors and regressor ONLY on training split
        pipe.fit(X_train, y_train)

        # In-sample diagnostics
        train_preds = pipe.predict(X_train)
        train_mae = float(np.mean(np.abs(train_preds - y_train)))
        if np.std(train_preds) > 1e-8 and np.std(y_train) > 1e-8:
            train_ic, _ = spearmanr(train_preds, y_train)
            if np.isnan(train_ic):
                train_ic = 0.0
        else:
            train_ic = 0.0


        # 5. Point-in-Time Prediction for Cross-Section at as_of_time
        preds_today = pipe.predict(X_today)
        slice_today["predicted_return"] = preds_today

        self.audit_logs.append(WalkForwardTrainAuditLog(
            prediction_date=as_of_date_str,
            training_start=training_start_str,
            training_end=training_end_str,
            sample_count=len(train_df),
            model_name=model_label,
            feature_count=len(feature_cols),
            train_mae=train_mae,
            train_ic=float(train_ic),
        ))

        return slice_today

