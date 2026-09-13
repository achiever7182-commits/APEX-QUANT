"""
core/strategies/ml_strategy.py — Machine Learning trading strategy.

Uses a scikit-learn classifier (RandomForest) to predict future price direction
from technical and statistical features engineered strictly from historical data.

CRITICAL LOOKAHEAD BIAS CONSTRAINT:
----------------------------------
All features are computed using ONLY data available up to and including the current
candle t (t, t-1, t-2, ...). Future candles (t+1, t+2, ...) are NEVER accessed during
feature calculation or prediction.
"""

from __future__ import annotations

import os
import math
from typing import Any

from core.strategy import MarketData, Signal, Strategy

try:
    import joblib
except ImportError:
    joblib = None

DEFAULT_MODEL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "models",
    "ml_model.joblib",
)


def extract_features_from_history(history: list[MarketData]) -> list[float] | None:
    """
    Compute feature vector from historical candles up to the current candle.

    CRITICAL: Uses ONLY candles available up to history[-1].
    Requires at least 35 candles to reliably compute 26-period EMA and 20-period stats.

    Features (11):
      1. return_1: 1-candle return
      2. return_5: 5-candle return
      3. return_10: 10-candle return
      4. return_20: 20-candle return
      5. volatility_20: standard deviation of 1-candle returns over 20 candles
      6. rsi_14: Relative Strength Index (14-period)
      7. macd_ratio: (12-EMA - 26-EMA) / close
      8. macd_signal_ratio: 9-EMA of MACD / close
      9. bb_percent_b: Bollinger %B position ((close - lower) / (upper - lower))
     10. volume_ratio_20: volume / 20-period average volume
     11. body_to_range: (close - open) / (high - low)
    """
    if len(history) < 35:
        return None

    # Use only the last 50 candles for feature calculations (no future candles exist here)
    window = history[-50:]
    closes = [c.close for c in window]
    volumes = [c.volume for c in window]
    latest = window[-1]

    curr_close = closes[-1]
    if curr_close <= 0:
        return None

    # 1-4. Returns over multiple lookback windows (backward-looking only)
    ret_1 = (curr_close - closes[-2]) / closes[-2] if len(closes) >= 2 else 0.0
    ret_5 = (curr_close - closes[-6]) / closes[-6] if len(closes) >= 6 else 0.0
    ret_10 = (curr_close - closes[-11]) / closes[-11] if len(closes) >= 11 else 0.0
    ret_20 = (curr_close - closes[-21]) / closes[-21] if len(closes) >= 21 else 0.0

    # 5. Volatility (std dev of 1-candle returns over last 20 candles)
    recent_closes = closes[-21:]
    returns_20 = [(recent_closes[i] - recent_closes[i - 1]) / recent_closes[i - 1] for i in range(1, len(recent_closes))]
    mean_ret = sum(returns_20) / len(returns_20) if returns_20 else 0.0
    var = sum((r - mean_ret) ** 2 for r in returns_20) / max(len(returns_20) - 1, 1)
    volatility_20 = math.sqrt(var)

    # 6. RSI (14-period Wilder smoothing)
    rsi_closes = closes[-15:]
    gains = []
    losses = []
    for i in range(1, len(rsi_closes)):
        diff = rsi_closes[i] - rsi_closes[i - 1]
        gains.append(diff if diff > 0 else 0.0)
        losses.append(-diff if diff < 0 else 0.0)
    avg_gain = sum(gains) / 14 if gains else 0.0
    avg_loss = sum(losses) / 14 if losses else 0.0
    if avg_loss == 0.0:
        rsi_14 = 100.0
    else:
        rs = avg_gain / avg_loss
        rsi_14 = 100.0 - (100.0 / (1.0 + rs))

    # 7-8. MACD (12-EMA, 26-EMA, 9-signal) normalized by close
    def calc_ema(series: list[float], period: int) -> float:
        k = 2.0 / (period + 1)
        ema = series[0]
        for val in series[1:]:
            ema = val * k + ema * (1.0 - k)
        return ema

    fast_ema = calc_ema(closes[-26:], 12)
    slow_ema = calc_ema(closes[-26:], 26)
    macd_val = fast_ema - slow_ema
    macd_ratio = macd_val / curr_close

    # Build brief historical MACD to estimate 9-period signal
    macd_series = []
    for offset in range(9, 0, -1):
        idx = len(closes) - offset
        sub_closes = closes[:idx]
        if len(sub_closes) >= 26:
            f = calc_ema(sub_closes[-26:], 12)
            s = calc_ema(sub_closes[-26:], 26)
            macd_series.append(f - s)
        else:
            macd_series.append(macd_val)
    macd_signal = calc_ema(macd_series, 9) if macd_series else macd_val
    macd_signal_ratio = macd_signal / curr_close

    # 9. Bollinger Bands %B (20-period, 2-std)
    bb_closes = closes[-20:]
    bb_mean = sum(bb_closes) / 20.0
    bb_var = sum((c - bb_mean) ** 2 for c in bb_closes) / 20.0
    bb_std = math.sqrt(bb_var)
    upper_band = bb_mean + 2.0 * bb_std
    lower_band = bb_mean - 2.0 * bb_std
    band_width = upper_band - lower_band
    bb_percent_b = (curr_close - lower_band) / band_width if band_width > 0 else 0.5

    # 10. Volume Ratio (current volume vs 20-period average volume)
    recent_vols = volumes[-20:]
    avg_vol = sum(recent_vols) / len(recent_vols) if recent_vols else 1.0
    volume_ratio_20 = latest.volume / avg_vol if avg_vol > 0 else 1.0

    # 11. Body to Range ratio
    candle_range = latest.high - latest.low
    body_to_range = (latest.close - latest.open) / candle_range if candle_range > 0 else 0.0

    return [
        ret_1,
        ret_5,
        ret_10,
        ret_20,
        volatility_20,
        rsi_14,
        macd_ratio,
        macd_signal_ratio,
        bb_percent_b,
        volume_ratio_20,
        body_to_range,
    ]


class MLStrategy(Strategy):
    """
    Machine Learning trading strategy using a pre-trained scikit-learn model.

    Evaluates engineered features against the trained model to predict the probability
    of future price appreciation.
    """

    def __init__(
        self,
        model_path: str = DEFAULT_MODEL_PATH,
        buy_threshold: float = 0.53,
        close_threshold: float = 0.48,
    ) -> None:
        super().__init__(name="ML_Strategy")
        self.model_path = model_path
        self.buy_threshold = buy_threshold
        self.close_threshold = close_threshold
        self._position_open = False
        self.model: Any = None
        self._load_model()

    def _load_model(self) -> None:
        """Load trained model bundle from disk. Raises informative error if missing."""
        if joblib is None:
            raise ImportError(
                "joblib or scikit-learn is not installed. Please run: pip install scikit-learn joblib"
            )

        if not os.path.exists(self.model_path):
            raise FileNotFoundError(
                f"\n[MLStrategy Error] Model file not found at: {self.model_path}\n"
                f"You must train an ML model before using this strategy.\n"
                f"Run the training script first:\n"
                f"    python train_ml_model.py\n"
            )

        bundle = joblib.load(self.model_path)
        if isinstance(bundle, dict) and "model" in bundle:
            self.model = bundle["model"]
            self.feature_names = bundle.get("feature_names", [])
        else:
            self.model = bundle
            self.feature_names = []

        if hasattr(self.model, "n_jobs"):
            self.model.n_jobs = 1


    def decide(self) -> Signal:
        """
        Produce BUY, CLOSE, or HOLD based on model prediction probability.
        Uses ONLY past candles in self.history (no lookahead bias).
        """
        features = extract_features_from_history(self.history)
        if features is None or self.model is None:
            return Signal.HOLD

        try:
            # predict_proba returns [[P(DOWN), P(UP)]]
            proba = self.model.predict_proba([features])[0]
            prob_up = float(proba[1])
        except Exception:
            return Signal.HOLD

        if prob_up >= self.buy_threshold and not self._position_open:
            self._position_open = True
            return Signal.BUY

        if prob_up < self.close_threshold and self._position_open:
            self._position_open = False
            return Signal.CLOSE

        return Signal.HOLD
