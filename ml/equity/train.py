"""
ml/equity/train.py — Training Pipeline and Experiment Runner for Equity ML.

Orchestrates:
  1. Chronological splitting of EquityMLDataset (Train, Validation, Test)
  2. Training Naive, Linear (Ridge), and Tree (RandomForest) models
  3. Strict isolation: Preprocessors fitted ONLY on training split
  4. Comprehensive evaluation against validation and test sets
  5. Cross-sectional Spearman IC and quantile spread evaluation
  6. Optional artifact registration into ModelRegistry
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd

from ml.equity.dataset import EquityMLDataset
from ml.equity.evaluate import EquityEvaluator, ModelEvaluationReport
from ml.equity.models import (
    IEquityModel,
    LinearEquityModel,
    NaiveBaselineModel,
    TreeEquityModel,
)
from ml.equity.registry import ModelArtifactMetadata, ModelRegistry
from ml.equity.split import ChronologicalSplitter, DatasetSplit

logger = logging.getLogger("apex_quant.ml.equity.train")


@dataclass
class TrainingResult:
    """Summary of training run across all models and splits."""
    models: Dict[str, IEquityModel]
    split: DatasetSplit
    val_reports: Dict[str, ModelEvaluationReport]
    test_reports: Dict[str, ModelEvaluationReport]
    best_model_name: str
    saved_artifact_version: Optional[str] = None
    feature_importances: Dict[str, Dict[str, float]] = field(default_factory=dict)


class EquityTrainer:
    """
    Automated training orchestrator for multi-stock equity ML models.
    """

    def __init__(
        self,
        registry: Optional[ModelRegistry] = None,
        random_state: int = 42,
    ):
        self.registry = registry or ModelRegistry()
        self.random_state = random_state

    def train_models(
        self,
        dataset: EquityMLDataset,
        train_ratio: float = 0.70,
        val_ratio: float = 0.15,
        test_ratio: float = 0.15,
        save_best: bool = True,
        save_tag: Optional[str] = None,
    ) -> TrainingResult:
        """
        Execute full training and evaluation workflow.

        Parameters:
            dataset: Pre-built EquityMLDataset.
            train_ratio, val_ratio, test_ratio: Chronological split ratios.
            save_best: If True, registers best model into ModelRegistry.
            save_tag: Optional tag for saved model artifact.
        """
        # 1. Chronological split
        split = ChronologicalSplitter.split(
            dataset.data,
            train_ratio=train_ratio,
            val_ratio=val_ratio,
            test_ratio=test_ratio,
            timestamp_col="timestamp",
        )

        logger.info(
            f"Dataset split chronologically: Train={split.train_rows}, "
            f"Val={split.val_rows}, Test={split.test_rows} rows."
        )

        feature_cols = dataset.feature_names
        target_col = dataset.target_name

        X_train = split.train_df[feature_cols]
        y_train = split.train_df[target_col]

        X_val = split.val_df[feature_cols]
        y_val = split.val_df[target_col]

        X_test = split.test_df[feature_cols]
        y_test = split.test_df[target_col]

        # 2. Instantiate candidate models
        models: Dict[str, IEquityModel] = {
            "Naive": NaiveBaselineModel(strategy="mean"),
            "Ridge": LinearEquityModel(alpha=10.0),
            "RandomForest": TreeEquityModel(
                n_estimators=100,
                max_depth=6,
                min_samples_leaf=20,
                random_state=self.random_state,
            ),
        }

        val_reports: Dict[str, ModelEvaluationReport] = {}
        test_reports: Dict[str, ModelEvaluationReport] = {}
        feature_importances: Dict[str, Dict[str, float]] = {}

        # 3. Train each model
        for name, model in models.items():
            logger.info(f"Fitting model '{name}' on training set...")
            model.fit(X_train, y_train)
            feature_importances[name] = model.get_feature_importance()

            # Validation evaluation
            val_preds = model.predict(X_val)
            val_eval_df = split.val_df[["timestamp", "symbol", target_col]].copy()
            val_eval_df["pred"] = val_preds
            # Attach naive predictions for relative comparison
            val_eval_df["naive_pred"] = models["Naive"].predict(X_val)
            val_rep = EquityEvaluator.evaluate_model(
                model_name=name,
                target_name=target_col,
                eval_df=val_eval_df,
                pred_col="pred",
                target_col=target_col,
                naive_pred_col="naive_pred",
            )
            val_reports[name] = val_rep

            # Test evaluation (held-out period)
            test_preds = model.predict(X_test)
            test_eval_df = split.test_df[["timestamp", "symbol", target_col]].copy()
            test_eval_df["pred"] = test_preds
            test_eval_df["naive_pred"] = models["Naive"].predict(X_test)
            test_rep = EquityEvaluator.evaluate_model(
                model_name=name,
                target_name=target_col,
                eval_df=test_eval_df,
                pred_col="pred",
                target_col=target_col,
                naive_pred_col="naive_pred",
            )
            test_reports[name] = test_rep

        # 4. Select best model based on validation Information Coefficient (or RMSE if IC is 0)
        # Higher IC indicates better cross-sectional rank ordering ability for Step 6
        best_name = "RandomForest"
        best_ic = -999.0
        for name, rep in val_reports.items():
            if name == "Naive":
                continue
            ic = rep.cross_sectional_metrics.mean_ic
            if ic > best_ic:
                best_ic = ic
                best_name = name

        # 5. Optionally save artifact to registry
        saved_version = None
        if save_best and self.registry is not None:
            best_model = models[best_name]
            best_val = val_reports[best_name]
            best_test = test_reports[best_name]

            # Parse target horizon from target_col (e.g. target_return_5d -> 5)
            horizon = 5
            try:
                horizon = int(target_col.split("_")[-1].replace("d", ""))
            except Exception:
                pass

            meta = ModelArtifactMetadata(
                model_name=best_name,
                version="",  # registry generates
                target_name=target_col,
                target_horizon=horizon,
                features=feature_cols,
                training_start=str(split.train_start),
                training_end=str(split.train_end),
                validation_start=str(split.val_start),
                validation_end=str(split.val_end),
                test_start=str(split.test_start),
                test_end=str(split.test_end),
                random_seed=self.random_state,
                metrics={
                    "val_mae": best_val.regression_metrics.mae,
                    "val_rmse": best_val.regression_metrics.rmse,
                    "val_mean_ic": best_val.cross_sectional_metrics.mean_ic,
                    "val_ic_ir": best_val.cross_sectional_metrics.ic_ir,
                    "test_mae": best_test.regression_metrics.mae,
                    "test_rmse": best_test.regression_metrics.rmse,
                    "test_mean_ic": best_test.cross_sectional_metrics.mean_ic,
                    "test_ic_ir": best_test.cross_sectional_metrics.ic_ir,
                },
            )
            saved_version = self.registry.save_artifact(best_model, meta, tag=save_tag)
            logger.info(f"Saved best model '{best_name}' as artifact {saved_version}.")

        return TrainingResult(
            models=models,
            split=split,
            val_reports=val_reports,
            test_reports=test_reports,
            best_model_name=best_name,
            saved_artifact_version=saved_version,
            feature_importances=feature_importances,
        )
