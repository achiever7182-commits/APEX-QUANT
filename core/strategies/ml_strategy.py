"""
core/strategies/ml_strategy.py — Machine Learning trading strategy.

Uses a scikit-learn classifier (RandomForest) with 3 classes (BUY, HOLD, SELL)
and strict backward-looking feature engineering.

CRITICAL LOOKAHEAD BIAS CONSTRAINT:
----------------------------------
All features are computed using ONLY data available up to and including the current
candle t (t, t-1, t-2, ...). Future candles (t+1, t+2, ...) are NEVER accessed during
feature calculation or prediction.
"""

from __future__ import annotations

import os
from typing import Any

from core.strategy import MarketData, Signal, Strategy
from ml.model import MLModel
from ml.predict import predict_candle, PredictionResult
import config

DEFAULT_MODEL_PATH = getattr(config, "ML_MODEL_PATH", "models/ml_model.joblib")


class MLStrategy(Strategy):
    """
    Machine Learning trading strategy using a pre-trained MLModel.

    Evaluates 20 engineered features strictly from historical candles up to candle t.
    Produces BUY, SELL, or HOLD decisions with confidence filtering.
    """

    def __init__(
        self,
        model_path: str = DEFAULT_MODEL_PATH,
        min_confidence: float | None = None,
        buy_threshold: float | None = None,
        close_threshold: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        model: MLModel | None = None,
    ) -> None:
        super().__init__(name="ML_Strategy")
        self.model_path = model_path
        self.min_confidence = (
            min_confidence
            if min_confidence is not None
            else getattr(config, "ML_MIN_CONFIDENCE", 0.60)
        )
        self.stop_loss = (
            stop_loss
            if stop_loss is not None
            else getattr(config, "STOP_LOSS", 0.015)
        )
        self.take_profit = (
            take_profit
            if take_profit is not None
            else getattr(config, "TAKE_PROFIT", 0.035)
        )

        self._position_open = False
        self.last_prediction: PredictionResult | None = None

        if model is not None:
            self.ml_model = model
            self.model = model.model
            self.feature_names = model.feature_names
        else:
            self.ml_model = None
            self.model = None
            self.feature_names = []
            if os.path.exists(self.model_path):
                self._load_model()

    def _load_model(self) -> None:
        """Load trained model bundle from disk."""
        if not os.path.exists(self.model_path):
            raise FileNotFoundError(
                f"\n[MLStrategy Error] Model file not found at: {self.model_path}\n"
                f"You must train an ML model before using this strategy.\n"
                f"Run the training script first:\n"
                f"    python ml/train.py\n"
            )
        self.ml_model = MLModel.load(self.model_path)
        self.model = self.ml_model.model
        self.feature_names = self.ml_model.feature_names

    def decide(self) -> Signal:
        """
        Produce BUY, CLOSE, or HOLD based on model prediction probability.
        Uses ONLY past candles in self.history (no lookahead bias).
        """
        if self.ml_model is None:
            if os.path.exists(self.model_path):
                self._load_model()
            else:
                return Signal.HOLD

        if len(self.history) < 35:
            return Signal.HOLD

        pred = predict_candle(self.ml_model, self.history, min_confidence=self.min_confidence)
        if pred is None:
            return Signal.HOLD

        self.last_prediction = pred

        # If model outputs BUY and position not open -> Signal.BUY
        if pred.signal == "BUY" and not self._position_open:
            self._position_open = True
            return Signal.BUY

        # If model outputs SELL and position open -> Signal.CLOSE
        if pred.signal == "SELL" and self._position_open:
            self._position_open = False
            return Signal.CLOSE

        return Signal.HOLD
