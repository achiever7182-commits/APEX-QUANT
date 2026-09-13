"""
train_ml_model.py — Train and evaluate a Machine Learning model for trading.

Fetches real historical Binance market data, engineers features with ZERO lookahead
bias, trains a RandomForestClassifier on chronological data, and validates on
unseen future data.

Usage:
    python train_ml_model.py                     # default: 180 days, 1h candles
    python train_ml_model.py --days 90 --timeframe 1h
    python train_ml_model.py --horizon 5 --days 180
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report

from adapters.binance_public_data_adapter import BinancePublicDataAdapter
from core.strategies.ml_strategy import extract_features_from_history

FEATURE_NAMES = [
    "return_1",
    "return_5",
    "return_10",
    "return_20",
    "volatility_20",
    "rsi_14",
    "macd_ratio",
    "macd_signal_ratio",
    "bb_percent_b",
    "volume_ratio_20",
    "body_to_range",
]

DEFAULT_MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
DEFAULT_MODEL_PATH = os.path.join(DEFAULT_MODEL_DIR, "ml_model.joblib")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train an ML model for price direction prediction.")
    parser.add_argument("--symbol", default="BTC/USDT", help="Trading pair (default: BTC/USDT)")
    parser.add_argument("--timeframe", default="1h", help="Candle timeframe (default: 1h)")
    parser.add_argument("--days", type=int, default=180, help="Days of historical data to fetch (default: 180)")
    parser.add_argument("--horizon", type=int, default=5, help="Candles ahead to predict (default: 5)")
    parser.add_argument("--train-ratio", type=float, default=0.75, help="Chronological train split ratio (default: 0.75)")
    parser.add_argument("--output", default=DEFAULT_MODEL_PATH, help=f"Path to save trained model (default: {DEFAULT_MODEL_PATH})")
    return parser.parse_args()


def build_dataset(candles, horizon: int = 5) -> tuple[np.ndarray, np.ndarray]:
    """
    Construct (X, y) feature matrix and labels with ZERO lookahead bias.

    CRITICAL LOOKAHEAD ENFORCEMENT:
    -------------------------------
    - At index i, features X[i] are computed strictly using candles[0 ... i].
    - Target label y[i] is defined as:
          1 if candles[i + horizon].close > candles[i].close else 0
    - The features X[i] have NO access to candle i+1 through i+horizon.
    """
    X_list: list[list[float]] = []
    y_list: list[int] = []

    total = len(candles)
    # Require at least 50 candles for warmup lookbacks
    start_idx = 50
    end_idx = total - horizon

    print(f"[ml_train] Engineering features for {end_idx - start_idx} sample points (horizon={horizon})...")

    for i in range(start_idx, end_idx):
        history_slice = candles[: i + 1]
        feat = extract_features_from_history(history_slice)
        if feat is None:
            continue

        # Target: Did close price increase H candles into the future?
        current_close = candles[i].close
        future_close = candles[i + horizon].close
        target = 1 if future_close > current_close else 0

        X_list.append(feat)
        y_list.append(target)

    return np.array(X_list), np.array(y_list)


def main() -> None:
    args = parse_args()

    print("=" * 70)
    print("  MACHINE LEARNING MODEL TRAINING (ZERO LOOKAHEAD BIAS)")
    print("=" * 70)
    print(f"Symbol:          {args.symbol}")
    print(f"Timeframe:       {args.timeframe}")
    print(f"History:         {args.days} days")
    print(f"Horizon:         {args.horizon} candles ahead")
    print(f"Train/Val Split: {args.train_ratio * 100:.0f}% train / {(1 - args.train_ratio) * 100:.0f}% validation")
    print()

    # 1. Fetch real historical data
    adapter = BinancePublicDataAdapter()
    candles = adapter.fetch_historical_candles(
        symbol=args.symbol,
        timeframe=args.timeframe,
        since_days_ago=args.days,
    )

    if len(candles) < 100:
        print(f"[ml_train] Error: Not enough candles ({len(candles)}). Need at least 100.")
        sys.exit(1)

    # 2. Build dataset
    X, y = build_dataset(candles, horizon=args.horizon)
    n_samples = len(X)
    print(f"[ml_train] Dataset built: {n_samples} total labeled samples.")

    # 3. Chronological split (DO NOT SHUFFLE - prevents temporal leakage)
    split_idx = int(n_samples * args.train_ratio)
    X_train, X_val = X[:split_idx], X[split_idx:]
    y_train, y_val = y[:split_idx], y[split_idx:]

    print(f"[ml_train] Chronological Split: {len(X_train)} training samples, {len(X_val)} validation samples.")
    train_up_pct = np.mean(y_train) * 100
    val_up_pct = np.mean(y_val) * 100
    print(f"[ml_train] Base rate (% UP): Train={train_up_pct:.1f}%, Validation={val_up_pct:.1f}%")
    print()

    # 4. Train RandomForestClassifier (interpretable, controlled tree depth)
    print("[ml_train] Training RandomForestClassifier (n_estimators=100, max_depth=4, min_samples_leaf=20)...")
    model = RandomForestClassifier(
        n_estimators=100,
        max_depth=4,
        min_samples_leaf=20,
        random_state=42,
        n_jobs=1,
    )
    model.fit(X_train, y_train)


    # 5. Evaluate training and validation accuracy
    y_train_pred = model.predict(X_train)
    y_val_pred = model.predict(X_val)

    train_acc = accuracy_score(y_train, y_train_pred)
    val_acc = accuracy_score(y_val, y_val_pred)

    print()
    print("-" * 55)
    print("  MODEL PERFORMANCE METRICS")
    print("-" * 55)
    print(f"  Training Accuracy:   {train_acc * 100:.2f}%")
    print(f"  Validation Accuracy: {val_acc * 100:.2f}%")
    print(f"  Accuracy Gap:        {(train_acc - val_acc) * 100:+.2f}%")
    print("-" * 55)

    # Overfitting diagnostic
    if (train_acc - val_acc) > 0.10:
        print("\n  [OVERFITTING WARNING] Training accuracy is significantly higher than validation accuracy!")
        print("  The model has memorized training noise. Features or hyperparameters should be regularized.")
    elif val_acc > 0.52:
        print("\n  [DIAGNOSTIC] Model shows a statistically positive validation edge (> 52%) on unseen future data.")
    else:
        print("\n  [DIAGNOSTIC] Validation accuracy is near baseline random walk (~50%). Typical for short-horizon financial returns.")

    # Feature importances
    print("\nFeature Importances:")
    importances = model.feature_importances_
    sorted_indices = np.argsort(importances)[::-1]
    for idx in sorted_indices:
        print(f"  {FEATURE_NAMES[idx]:<20} {importances[idx] * 100:5.1f}%")

    # 6. Save model bundle
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    bundle = {
        "model": model,
        "feature_names": FEATURE_NAMES,
        "horizon": args.horizon,
        "symbol": args.symbol,
        "timeframe": args.timeframe,
        "training_time": datetime.now().isoformat(),
        "train_accuracy": float(train_acc),
        "validation_accuracy": float(val_acc),
    }
    joblib.dump(bundle, args.output)
    print(f"\n[ml_train] Saved trained model to: {args.output}")


if __name__ == "__main__":
    main()
