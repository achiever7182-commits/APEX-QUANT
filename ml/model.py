"""
ml/model.py — Tabular ML model wrapper with 3-class probability output & confidence filtering.
"""

from __future__ import annotations

import json
import os
from typing import Any
import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier

from ml.dataset import LABEL_BUY, LABEL_HOLD, LABEL_SELL


class MLModel:
    """
    Practical tabular model wrapper producing 3-class probabilities (BUY, HOLD, SELL).
    Enforces configurable confidence filtering to avoid trading low-certainty candles.
    """

    def __init__(
        self,
        feature_names: list[str] | None = None,
        min_confidence: float = 0.60,
        n_estimators: int = 100,
        max_depth: int = 5,
        min_samples_leaf: int = 20,
        random_state: int = 42,
    ) -> None:
        self.feature_names = feature_names or []
        self.min_confidence = min_confidence
        self.model = RandomForestClassifier(
            n_estimators=n_estimators,
            max_depth=max_depth,
            min_samples_leaf=min_samples_leaf,
            random_state=random_state,
            class_weight="balanced",
            n_jobs=1,
        )
        self.classes_ = np.array([LABEL_SELL, LABEL_HOLD, LABEL_BUY])
        self.is_trained = False

    def fit(self, X: np.ndarray, y: np.ndarray) -> MLModel:
        """Train the underlying classifier on X, y."""
        self.model.fit(X, y)
        self.classes_ = self.model.classes_
        self.is_trained = True
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """
        Return probabilities mapped strictly to [P(SELL), P(HOLD), P(BUY)].
        """
        if not self.is_trained:
            raise RuntimeError("Model is not trained yet. Call fit() or load() first.")

        raw_proba = self.model.predict_proba(X)
        # Ensure 3-class alignment [SELL, HOLD, BUY] even if a class was absent in training
        n_samples = len(X)
        aligned = np.zeros((n_samples, 3), dtype=np.float32)
        # Default neutral prior if any class missing
        aligned[:, LABEL_HOLD] = 1.0

        for col_idx, cls_label in enumerate(self.classes_):
            if cls_label in (LABEL_SELL, LABEL_HOLD, LABEL_BUY):
                aligned[:, int(cls_label)] = raw_proba[:, col_idx]

        return aligned

    def predict_signal(
        self,
        features: list[float] | np.ndarray,
        min_confidence: float | None = None,
    ) -> tuple[str, float, dict[str, float], str]:
        """
        Produce a trading decision on a single feature vector.

        Returns:
            (signal, confidence, probabilities_dict, reason)
        """
        threshold = self.min_confidence if min_confidence is None else min_confidence
        X = np.asarray(features, dtype=np.float32).reshape(1, -1)
        proba = self.predict_proba(X)[0]

        p_sell = float(proba[LABEL_SELL])
        p_hold = float(proba[LABEL_HOLD])
        p_buy = float(proba[LABEL_BUY])

        probs_dict = {
            "BUY": round(p_buy, 4),
            "HOLD": round(p_hold, 4),
            "SELL": round(p_sell, 4),
        }

        # Highest probability class
        class_idx = int(np.argmax(proba))
        confidence = float(proba[class_idx])

        # Enforce statistical conviction: must be highest class and meet confidence threshold with clear spread
        spread = p_buy - p_sell

        if class_idx == LABEL_BUY and confidence >= threshold and spread >= 0.10:
            signal = "BUY"
            reason = f"High conviction bullish signal (BUY: {p_buy * 100:.1f}%, HOLD: {p_hold * 100:.1f}%, SELL: {p_sell * 100:.1f}%, spread: +{spread * 100:.1f}%)."
        elif class_idx == LABEL_SELL and confidence >= threshold and spread <= -0.10:
            signal = "SELL"
            reason = f"High conviction bearish signal (SELL: {p_sell * 100:.1f}%, HOLD: {p_hold * 100:.1f}%, BUY: {p_buy * 100:.1f}%, spread: {spread * 100:.1f}%)."
        else:
            signal = "HOLD"
            if class_idx == LABEL_BUY:
                reason = f"Bullish bias (BUY: {p_buy * 100:.1f}%), but confidence or spread below threshold ({threshold * 100:.0f}%). Filtering to HOLD."
            elif class_idx == LABEL_SELL:
                reason = f"Bearish bias (SELL: {p_sell * 100:.1f}%), but confidence or spread below threshold ({threshold * 100:.0f}%). Filtering to HOLD."
            else:
                reason = f"Market is neutral/ranging (HOLD probability: {p_hold * 100:.1f}%)."

        return signal, confidence, probs_dict, reason

    def save(self, path: str, metadata: dict[str, Any] | None = None) -> None:
        """Save model bundle to disk and write companion metadata JSON."""
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        bundle = {
            "model": self.model,
            "feature_names": self.feature_names,
            "classes": self.classes_,
            "min_confidence": self.min_confidence,
            "is_trained": self.is_trained,
        }
        joblib.dump(bundle, path)

        if metadata:
            meta_path = os.path.splitext(path)[0] + "_metadata.json"
            try:
                with open(meta_path, "w", encoding="utf-8") as f:
                    json.dump(metadata, f, indent=2)
            except Exception as err:
                print(f"[model] Warning: Could not write metadata to {meta_path}: {err}")

    @classmethod
    def load(cls, path: str) -> MLModel:
        """Load trained model bundle from disk."""
        if not os.path.exists(path):
            raise FileNotFoundError(f"Model file not found at: {path}")

        bundle = joblib.load(path)
        instance = cls()
        if isinstance(bundle, dict) and "model" in bundle:
            instance.model = bundle["model"]
            instance.feature_names = bundle.get("feature_names", [])
            instance.classes_ = bundle.get("classes", np.array([LABEL_SELL, LABEL_HOLD, LABEL_BUY]))
            instance.min_confidence = bundle.get("min_confidence", 0.60)
            instance.is_trained = bundle.get("is_trained", True)
        else:
            instance.model = bundle
            instance.is_trained = True

        return instance
