"""
ml/predict.py — Real-time and sequential candle inference engine.

Applies feature extraction on past candles up to candle t, checks model confidence,
and formats trading decision signals.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence
from core.strategy import MarketData
from ml.feature_engineering import extract_features_single
from ml.model import MLModel


@dataclass
class PredictionResult:
    signal: str                 # "BUY", "SELL", or "HOLD"
    confidence: float           # 0.0 to 1.0
    buy_probability: float
    hold_probability: float
    sell_probability: float
    reason: str
    timestamp: int
    price: float


def predict_candle(
    model: MLModel,
    history: Sequence[MarketData],
    min_confidence: float | None = None,
) -> PredictionResult | None:
    """
    Extract features strictly up to history[-1] and produce an AI prediction.
    Returns None if history has fewer than 35 candles (warmup period).
    """
    if len(history) < 35:
        return None

    features = extract_features_single(history)
    if features is None:
        return None

    latest_candle = history[-1]
    signal, conf, probs, reason = model.predict_signal(features, min_confidence=min_confidence)

    return PredictionResult(
        signal=signal,
        confidence=conf,
        buy_probability=probs.get("BUY", 0.0),
        hold_probability=probs.get("HOLD", 0.0),
        sell_probability=probs.get("SELL", 0.0),
        reason=reason,
        timestamp=latest_candle.timestamp,
        price=float(latest_candle.close),
    )


def format_prediction_box(pred: PredictionResult, symbol: str = "BTC/USDT") -> str:
    """Format AI prediction output matching trading terminal standards."""
    clean_sym = symbol.replace("/", "")
    lines = [
        "--------------------------------------------------",
        "  AI TRADING SIGNAL",
        "--------------------------------------------------",
        f"Symbol:     {clean_sym}",
        f"Price:      ${pred.price:,.2f}",
        f"Signal:     {pred.signal}",
        f"Confidence: {pred.confidence * 100:.1f}%",
        "",
        f"BUY probability:  {pred.buy_probability * 100:.1f}%",
        f"HOLD probability: {pred.hold_probability * 100:.1f}%",
        f"SELL probability: {pred.sell_probability * 100:.1f}%",
        "",
        "Reason:",
        f"{pred.reason}",
        "--------------------------------------------------",
    ]
    return "\n".join(lines)
