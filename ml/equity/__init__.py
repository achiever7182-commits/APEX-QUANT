"""
ml/equity — APEX QUANT Cross-Sectional ML Prediction Subsystem for Indian Equities.

Provides:
  - Target generation for forward returns (regression & classification)
  - Survivorship-bias-free ML dataset building with Point-in-Time universe filtering
  - Chronological and walk-forward train/val/test splitting
  - Tabular baselines (Naive, Ridge, RandomForest)
  - Comprehensive time-series and cross-sectional Spearman IC evaluation
  - Versioned model artifact registry (models/equity/)
  - Multi-stock production inference
"""

from ml.equity.targets import TargetGenerator
from ml.equity.dataset import EquityMLDataset, EquityMLDatasetBuilder
from ml.equity.split import ChronologicalSplitter, DatasetSplit, WalkForwardSplitter
from ml.equity.models import (
    IEquityModel,
    LinearEquityModel,
    NaiveBaselineModel,
    TreeEquityModel,
)
from ml.equity.evaluate import (
    CrossSectionalMetrics,
    EquityEvaluator,
    ModelEvaluationReport,
    RegressionMetrics,
)
from ml.equity.registry import ModelArtifactMetadata, ModelRegistry
from ml.equity.train import EquityTrainer, TrainingResult
from ml.equity.predict import EquityPredictor

__all__ = [
    "TargetGenerator",
    "EquityMLDataset",
    "EquityMLDatasetBuilder",
    "ChronologicalSplitter",
    "DatasetSplit",
    "WalkForwardSplitter",
    "IEquityModel",
    "NaiveBaselineModel",
    "LinearEquityModel",
    "TreeEquityModel",
    "RegressionMetrics",
    "CrossSectionalMetrics",
    "ModelEvaluationReport",
    "EquityEvaluator",
    "ModelArtifactMetadata",
    "ModelRegistry",
    "EquityTrainer",
    "TrainingResult",
    "EquityPredictor",
]
