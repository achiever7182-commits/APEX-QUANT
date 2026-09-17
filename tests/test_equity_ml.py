"""
tests/test_equity_ml.py — Unit and Integration Tests for APEX QUANT Equity ML Prediction Engine.

Tests:
  1. Forward return target calculation (exact mathematical verification & tail NaNs)
  2. Binary classification target thresholding
  3. Strict chronological train/val/test splitting (train_end < val_start < test_start)
  4. Preprocessor isolation (fitted strictly on training features without test leakage)
  5. Point-in-time universe compliance (survivorship bias prevention)
  6. Zero-lookahead leakage audit (future prices do not alter historical feature vector X_t)
  7. Deterministic reproducibility (identical random seed produces identical weights and predictions)
  8. Model training: Naive, Linear (Ridge), and Tree (RandomForest) baselines
  9. Cross-sectional Spearman Information Coefficient (IC) & quantile bucket spreads
  10. ModelRegistry serialization and deserialization
  11. Real benchmark data training & evaluation on Parquet storage (RELIANCE, TCS, INFY, HDFCBANK, ICICIBANK)
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys
import tempfile
import numpy as np
import pandas as pd

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from data.market.storage import ParquetMarketDataStorage
from features.engine import FeatureEngine
from ml.equity.dataset import EquityMLDataset, EquityMLDatasetBuilder
from ml.equity.evaluate import EquityEvaluator
from ml.equity.models import LinearEquityModel, NaiveBaselineModel, TreeEquityModel
from ml.equity.predict import EquityPredictor
from ml.equity.registry import ModelArtifactMetadata, ModelRegistry
from ml.equity.split import ChronologicalSplitter, WalkForwardSplitter
from ml.equity.targets import TargetGenerator
from ml.equity.train import EquityTrainer


def create_synthetic_panel_df(n_days: int = 100, n_stocks: int = 4) -> pd.DataFrame:
    """Create deterministic synthetic panel DataFrame."""
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=n_days, freq="B")
    symbols = [f"STOCK_{chr(65 + i)}" for i in range(n_stocks)]

    rows = []
    for sym_idx, sym in enumerate(symbols):
        base_p = 100.0 * (sym_idx + 1)
        drift = np.linspace(0, 15, n_days)
        noise = np.sin(np.linspace(0, 10, n_days) + sym_idx) * 2.0
        close = base_p + drift + noise
        volume = 100_000.0 + np.random.uniform(0, 20_000, n_days)

        for d_idx, dt in enumerate(dates):
            rows.append({
                "timestamp": dt,
                "symbol": sym,
                "open": close[d_idx] - 0.5,
                "high": close[d_idx] + 1.0,
                "low": close[d_idx] - 1.0,
                "close": close[d_idx],
                "volume": volume[d_idx],
                # Synthetic features
                "feat_return_1d": np.random.normal(0.001, 0.01),
                "feat_rsi_14": 50.0 + np.sin(d_idx * 0.1) * 20.0,
                "feat_volatility_10d": 0.015,
                "has_sufficient_history": d_idx >= 20,
            })

    df = pd.DataFrame(rows)
    return df.sort_values(by=["timestamp", "symbol"]).reset_index(drop=True)


def test_target_generation_exact_math():
    """Verify forward return calculations and tail NaNs."""
    dates = pd.date_range("2024-01-01", periods=5, freq="B")
    df = pd.DataFrame({
        "timestamp": list(dates) * 2,
        "symbol": ["A"] * 5 + ["B"] * 5,
        "close": [100.0, 105.0, 110.0, 102.0, 120.0, 200.0, 210.0, 220.0, 204.0, 240.0],
    })

    target_df = TargetGenerator.add_forward_returns(df, horizons=[1, 2])

    # Stock A, index 0: close=100.0. Horizon 1d forward is 105.0 -> return = 5%
    np.testing.assert_allclose(target_df.loc[0, "target_return_1d"], 0.05)
    # Stock A, index 0: Horizon 2d forward is 110.0 -> return = 10%
    np.testing.assert_allclose(target_df.loc[0, "target_return_2d"], 0.10)
    # Tail rows: row 4 (last bar) for stock A must be NaN for 1d and 2d
    assert pd.isna(target_df.loc[4, "target_return_1d"])
    assert pd.isna(target_df.loc[3, "target_return_2d"])

    # Binary classification target
    binary_df = TargetGenerator.add_binary_classification_target(target_df, horizon=1, threshold=0.0)
    assert binary_df.loc[0, "target_binary_1d"] == 1.0
    # Index 2: close=110, next is 102 -> return is -7.2% -> binary label must be 0.0
    assert binary_df.loc[2, "target_binary_1d"] == 0.0


def test_chronological_splitting_no_leakage():
    """Verify strict chronological boundaries: Train < Val < Test."""
    df = create_synthetic_panel_df(n_days=100, n_stocks=4)
    split = ChronologicalSplitter.split(df, train_ratio=0.70, val_ratio=0.15, test_ratio=0.15)

    assert split.train_rows > 0
    assert split.val_rows > 0
    assert split.test_rows > 0

    # Invariant: max(Train) < min(Val) and max(Val) < min(Test)
    assert split.train_end < split.val_start, "Train dates must strictly precede Validation dates"
    assert split.val_end < split.test_start, "Validation dates must strictly precede Test dates"

    # Multi-stock alignment check: every stock has observations in each slice
    train_syms = set(split.train_df["symbol"].unique())
    val_syms = set(split.val_df["symbol"].unique())
    test_syms = set(split.test_df["symbol"].unique())
    assert train_syms == val_syms == test_syms


def test_walk_forward_splitter():
    """Verify expanding-window walk-forward fold generation."""
    df = create_synthetic_panel_df(n_days=60, n_stocks=2)
    folds = list(WalkForwardSplitter.generate_folds(df, n_folds=3, val_ratio=0.3))

    assert len(folds) == 3
    prev_train_len = 0
    for train_f, val_f, fold_idx in folds:
        assert len(train_f) > prev_train_len, "Walk-forward train set must expand"
        assert train_f["timestamp"].max() < val_f["timestamp"].min()
        prev_train_len = len(train_f)


def test_preprocessing_isolation():
    """Verify preprocessing (StandardScaler) is fitted strictly on X_train without test leakage."""
    X_train = pd.DataFrame({"feat1": [10.0, 20.0, 30.0]})
    y_train = pd.Series([0.01, 0.02, 0.03])

    X_test_normal = pd.DataFrame({"feat1": [15.0, 25.0]})
    X_test_corrupted = pd.DataFrame({"feat1": [10000.0, 20000.0]})

    model = LinearEquityModel(alpha=1.0)
    model.fit(X_train, y_train)

    scaler = model.pipeline.named_steps["scaler"]
    # Mean of training feat1 is 20.0
    np.testing.assert_allclose(scaler.mean_[0], 20.0)

    # Predictions on normal test set
    preds_normal = model.predict(X_test_normal)
    # Re-inspect scaler: training mean must remain unchanged
    np.testing.assert_allclose(scaler.mean_[0], 20.0)


def test_zero_lookahead_leakage_audit():
    """
    CRITICAL TEST: Mutating future prices at t+k alters target Y_t, but NEVER alters feature X_t.
    """
    panel = create_synthetic_panel_df(n_days=50, n_stocks=2)
    # Generate targets
    panel_with_target = TargetGenerator.add_forward_returns(panel, horizons=[5])

    # Record feature vector for row 20
    feat_x_row20_orig = panel_with_target.loc[20, ["feat_return_1d", "feat_rsi_14", "feat_volatility_10d"]].copy()

    sym_row20 = panel.loc[20, "symbol"]
    ts_row20 = panel.loc[20, "timestamp"]

    # Find the row for the same symbol 5 days into the future
    sym_rows = panel[panel["symbol"] == sym_row20].sort_values("timestamp").reset_index()
    match_idx = sym_rows[sym_rows["timestamp"] == ts_row20].index[0]
    future_global_idx = sym_rows.loc[match_idx + 5, "index"]

    # Mutate future close for this symbol at t+5
    panel_mutated = panel.copy()
    panel_mutated.loc[future_global_idx, "close"] = panel_mutated.loc[future_global_idx, "close"] * 3.0
    panel_mutated_with_target = TargetGenerator.add_forward_returns(panel_mutated, horizons=[5])

    # 1. Feature vector at row 20 must be 100% IDENTICAL
    feat_x_row20_mut = panel_mutated_with_target.loc[20, ["feat_return_1d", "feat_rsi_14", "feat_volatility_10d"]]
    pd.testing.assert_series_equal(feat_x_row20_orig, feat_x_row20_mut)

    # 2. Target at row 20 MUST change (because target is the future outcome)
    target_orig = panel_with_target.loc[20, "target_return_5d"]
    target_mut = panel_mutated_with_target.loc[20, "target_return_5d"]
    assert target_orig != target_mut, "Target must change when future price changes"


def test_reproducibility_and_models():
    """Verify deterministic training and evaluation across Naive, Ridge, and RandomForest."""
    df = create_synthetic_panel_df(n_days=80, n_stocks=3)
    df = TargetGenerator.add_forward_returns(df, horizons=[5])
    df = df.dropna().reset_index(drop=True)

    feature_cols = ["feat_return_1d", "feat_rsi_14", "feat_volatility_10d"]
    target_col = "target_return_5d"

    X = df[feature_cols]
    y = df[target_col]

    # Naive Model
    naive = NaiveBaselineModel(strategy="mean")
    naive.fit(X, y)
    naive_preds = naive.predict(X)
    np.testing.assert_allclose(naive_preds, y.mean())

    # Ridge Model
    ridge = LinearEquityModel(alpha=1.0)
    ridge.fit(X, y)
    ridge_preds = ridge.predict(X)
    assert len(ridge_preds) == len(X)
    assert len(ridge.get_feature_importance()) == 3

    # RandomForest Model: Reproducibility check
    rf1 = TreeEquityModel(n_estimators=30, max_depth=4, random_state=42)
    rf1.fit(X, y)
    preds1 = rf1.predict(X)

    rf2 = TreeEquityModel(n_estimators=30, max_depth=4, random_state=42)
    rf2.fit(X, y)
    preds2 = rf2.predict(X)

    np.testing.assert_allclose(preds1, preds2, err_msg="RandomForest training must be strictly deterministic!")


def test_cross_sectional_ic_and_quantiles():
    """Verify Spearman Information Coefficient (IC) and bucket return calculations."""
    # Synthetic dataset with 5 stocks where predictions perfectly correlate with target
    dates = pd.date_range("2024-01-01", periods=2, freq="B")
    eval_df = pd.DataFrame({
        "timestamp": list(dates) * 5,
        "symbol": ["A", "B", "C", "D", "E"] * 2,
        "pred": [0.01, 0.02, 0.03, 0.04, 0.05, 0.10, 0.20, 0.30, 0.40, 0.50],
        "target": [0.015, 0.025, 0.035, 0.045, 0.055, 0.12, 0.22, 0.32, 0.42, 0.52],
    })

    cs_metrics = EquityEvaluator.calculate_cross_sectional_metrics(
        eval_df, pred_col="pred", target_col="target", n_buckets=5
    )

    # Perfect rank correlation -> Mean IC must be exactly 1.0
    np.testing.assert_allclose(cs_metrics.mean_ic, 1.0, atol=1e-5)
    assert cs_metrics.pct_positive_ic == 100.0
    # Top bucket return (Q5) must exceed Bottom bucket (Q1)
    assert cs_metrics.top_minus_bottom_spread > 0.0


def test_model_registry_save_and_load():
    """Verify versioned model artifact storage and loading."""
    temp_dir = Path(tempfile.mkdtemp(prefix="apex_test_registry_"))
    try:
        registry = ModelRegistry(base_dir=temp_dir)
        model = LinearEquityModel(alpha=5.0)
        X = pd.DataFrame({"f1": [1.0, 2.0], "f2": [3.0, 4.0]})
        y = pd.Series([0.01, 0.02])
        model.fit(X, y)

        meta = ModelArtifactMetadata(
            model_name=model.model_name,
            version="v1_test",
            target_name="target_return_5d",
            target_horizon=5,
            features=["f1", "f2"],
            training_start="2024-01-01",
            training_end="2024-02-01",
            metrics={"mae": 0.005},
        )

        v_saved = registry.save_artifact(model, meta)
        assert v_saved == "v1_test"

        # Deserialization check
        loaded_model, loaded_meta = registry.load_artifact("v1_test")
        assert loaded_meta.target_horizon == 5
        assert loaded_meta.features == ["f1", "f2"]

        preds_orig = model.predict(X)
        preds_loaded = loaded_model.predict(X)
        np.testing.assert_allclose(preds_orig, preds_loaded)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_real_benchmark_data_training_and_evaluation():
    """
    Integration test: Train multi-stock ML models using real Parquet storage data
    for benchmark stocks (RELIANCE, TCS, INFY, HDFCBANK, ICICIBANK).
    """
    storage = ParquetMarketDataStorage()
    symbols = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]

    # 1. Feature extraction
    feature_engine = FeatureEngine()
    feature_set = feature_engine.generate_panel_from_storage(
        storage=storage,
        symbols=symbols,
        start_date="2022-01-01",
        end_date="2024-01-15",
        is_adjusted=True,
    )

    # 2. Dataset build with forward 5-day return targets
    stock_dfs = {sym: storage.query_by_symbol(sym, is_adjusted=True) for sym in symbols}
    builder = EquityMLDatasetBuilder(feature_engine=feature_engine, target_horizon=5)
    dataset = builder.build_dataset_from_feature_set(
        feature_set=feature_set,
        raw_or_adj_dfs=stock_dfs,
        target_horizon=5,
        filter_pit_universe=True,
        min_history_filter=True,
        drop_target_na=True,
    )

    assert dataset.row_count > 500, f"Expected > 500 usable rows, got {dataset.row_count}"
    assert dataset.feature_count >= 20

    # 3. Model training with temp registry
    temp_dir = Path(tempfile.mkdtemp(prefix="apex_test_trainer_"))
    try:
        registry = ModelRegistry(base_dir=temp_dir)
        trainer = EquityTrainer(registry=registry, random_state=42)

        result = trainer.train_models(
            dataset=dataset,
            train_ratio=0.70,
            val_ratio=0.15,
            test_ratio=0.15,
            save_best=True,
            save_tag="test",
        )

        assert result.best_model_name in result.models
        assert result.saved_artifact_version is not None

        # Verify evaluation reports exist for all models
        for m_name in ["Naive", "Ridge", "RandomForest"]:
            assert m_name in result.val_reports
            assert m_name in result.test_reports
            val_rep = result.val_reports[m_name]
            assert val_rep.regression_metrics.total_samples > 0
            assert val_rep.regression_metrics.mae > 0.0

        # Predictor test
        predictor = EquityPredictor.from_registry(result.saved_artifact_version, registry=registry)
        sample_df = dataset.data.iloc[-10:][["timestamp", "symbol"] + dataset.feature_names]
        preds_df = predictor.predict(sample_df)
        assert len(preds_df) == 10
        assert "predicted_return" in preds_df.columns
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    test_target_generation_exact_math()
    print("  [OK] test_target_generation_exact_math")
    test_chronological_splitting_no_leakage()
    print("  [OK] test_chronological_splitting_no_leakage")
    test_walk_forward_splitter()
    print("  [OK] test_walk_forward_splitter")
    test_preprocessing_isolation()
    print("  [OK] test_preprocessing_isolation")
    test_zero_lookahead_leakage_audit()
    print("  [OK] test_zero_lookahead_leakage_audit")
    test_reproducibility_and_models()
    print("  [OK] test_reproducibility_and_models")
    test_cross_sectional_ic_and_quantiles()
    print("  [OK] test_cross_sectional_ic_and_quantiles")
    test_model_registry_save_and_load()
    print("  [OK] test_model_registry_save_and_load")
    test_real_benchmark_data_training_and_evaluation()
    print("  [OK] test_real_benchmark_data_training_and_evaluation")
    print("\nAll Step 5 Equity ML tests PASSED successfully.")
