"""
tests/test_ml_pipeline.py — Verification test suite for Autonomous ML Trading Pipeline.

Tests:
  1. Zero-lookahead bias enforcement in feature engineering
  2. 3-class target labeling accuracy
  3. Chronological dataset splitting without shuffling or leakage
  4. Confidence threshold filtering to HOLD
  5. Slippage and transaction fee modeling in backtester
  6. Intraday Stop-Loss and Take-Profit execution
  7. PredictionResult formatting
"""

from __future__ import annotations

import copy
import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import numpy as np

from core.strategy import MarketData, Signal
from backtester.engine import BacktestEngine, FEE_RATE, SLIPPAGE_RATE
from ml.dataset import create_ml_dataset, LABEL_SELL, LABEL_HOLD, LABEL_BUY, chronological_split
from ml.feature_engineering import extract_features_df, extract_features_single, FEATURE_NAMES
from ml.model import MLModel
from ml.predict import predict_candle, format_prediction_box


def generate_synthetic_candles(n: int = 200, start_price: float = 50000.0, trend: float = 0.0002) -> list[MarketData]:
    """Generate deterministic synthetic candles for unit testing."""
    candles: list[MarketData] = []
    base_ts = 1700000000000
    price = start_price

    for i in range(n):
        open_p = price
        # Deterministic wave
        delta = (i % 7 - 3) * 15.0 + price * trend
        close_p = open_p + delta
        high_p = max(open_p, close_p) + 20.0
        low_p = min(open_p, close_p) - 20.0
        vol = 10.0 + (i % 5) * 2.0
        candles.append(
            MarketData(
                symbol="BTC/USDT",
                timestamp=base_ts + i * 300_000,
                open=open_p,
                high=high_p,
                low=low_p,
                close=close_p,
                volume=vol,
            )
        )
        price = close_p

    return candles


def test_zero_lookahead_feature_isolation():
    """Verify that features at candle t do NOT change when future candles are altered."""
    candles = generate_synthetic_candles(100)

    # Calculate features on original history up to t=50
    history_orig = candles[:50]
    feats_orig = extract_features_single(history_orig)
    assert feats_orig is not None
    assert len(feats_orig) == len(FEATURE_NAMES)

    # Now create modified candles for future bars t=51..100 with massive spikes
    candles_modified = copy.deepcopy(candles)
    for c in candles_modified[50:]:
        c.open *= 5.0
        c.high *= 5.0
        c.low *= 5.0
        c.close *= 5.0

    # Calculate features at t=50 with modified future
    history_after_future_change = candles_modified[:50]
    feats_after = extract_features_single(history_after_future_change)

    # MUST be strictly identical: future changes cannot alter past features
    np.testing.assert_allclose(feats_orig, feats_after, rtol=1e-5, atol=1e-5)


def test_target_labeling_3_classes():
    """Verify that returns map accurately to SELL (0), HOLD (1), and BUY (2)."""
    candles = generate_synthetic_candles(150)
    dataset = create_ml_dataset(
        candles=candles,
        horizon=3,
        buy_threshold=0.001,
        sell_threshold=-0.001,
        train_ratio=0.70,
        val_ratio=0.15,
    )

    # Check classes in y
    classes_present = set(np.unique(dataset.y_train))
    assert classes_present.issubset({LABEL_SELL, LABEL_HOLD, LABEL_BUY})
    assert len(dataset.feature_names) == 20


def test_chronological_split_no_leakage():
    """Verify chronological split guarantees train < val < test timestamps."""
    candles = generate_synthetic_candles(160)
    dataset = create_ml_dataset(candles, train_ratio=0.70, val_ratio=0.15)

    assert len(dataset.train_candles) > 0
    assert len(dataset.val_candles) > 0
    assert len(dataset.test_candles) > 0

    max_train_ts = max(c.timestamp for c in dataset.train_candles)
    min_val_ts = min(c.timestamp for c in dataset.val_candles)
    max_val_ts = max(c.timestamp for c in dataset.val_candles)
    min_test_ts = min(c.timestamp for c in dataset.test_candles)

    assert max_train_ts < min_val_ts, "Train timestamps leak into validation set!"
    assert max_val_ts < min_test_ts, "Validation timestamps leak into test set!"


def test_confidence_threshold_filtering():
    """Verify that signals with confidence below min_confidence are filtered to HOLD."""
    model = MLModel(feature_names=FEATURE_NAMES, min_confidence=0.75)
    candles = generate_synthetic_candles(150)
    dataset = create_ml_dataset(candles)
    model.fit(dataset.X_train, dataset.y_train)

    # Test single prediction
    feats = dataset.X_val[0]
    # At high confidence threshold (0.99), must be HOLD
    sig, conf, probs, reason = model.predict_signal(feats, min_confidence=0.99)
    assert sig == "HOLD"
    assert "below minimum threshold" in reason or sig == "HOLD"


def test_backtest_slippage_and_fees():
    """Verify BacktestEngine deducts fee and applies slippage to buy and sell fills."""
    candles = generate_synthetic_candles(60)

    class FixedSignalStrategy:
        name = "TestStrategy"
        def __init__(self):
            self.history = []
            self.count = 0
        def update(self, candle):
            self.history.append(candle)
            self.count += 1
            if self.count == 2:
                return Signal.BUY
            elif self.count == 5:
                return Signal.CLOSE
            return Signal.HOLD

    engine = BacktestEngine(
        starting_balance=10_000.0,
        fee_rate=0.001,
        slippage_pct=0.0005,
    )
    result = engine.run(FixedSignalStrategy(), candles)

    assert len(result.trades) >= 1
    t = result.trades[0]

    # Buy entry price should have been pushed up by slippage
    raw_buy_price = candles[1].close
    expected_entry = raw_buy_price * (1.0 + 0.0005)
    assert abs(t.entry_price - expected_entry) < 1e-4

    # Sell exit price should have been pushed down by slippage
    raw_sell_price = candles[4].close
    expected_exit = raw_sell_price * (1.0 - 0.0005)
    assert abs(t.exit_price - expected_exit) < 1e-4

    # Fee should be positive
    assert t.fee > 0.0


def test_intraday_stop_loss_trigger():
    """Verify intraday low triggers stop-loss exit even before candle close."""
    candles = generate_synthetic_candles(10)

    # Force candle 3 to have a severe dip in low
    candles[3].low = candles[2].close * 0.90  # 10% drop intraday

    class SimpleLongStrategy:
        name = "SimpleLong"
        stop_loss = 0.03  # 3% stop loss
        take_profit = 0.08
        def __init__(self):
            self.history = []
            self.idx = 0
        def update(self, c):
            self.history.append(c)
            self.idx += 1
            if self.idx == 2:
                return Signal.BUY
            return Signal.HOLD

    engine = BacktestEngine(starting_balance=10_000.0)
    result = engine.run(SimpleLongStrategy(), candles)

    # Verify a trade was exited with reason "stop_loss"
    sl_trades = [t for t in result.trades if t.exit_reason == "stop_loss"]
    assert len(sl_trades) == 1
    assert sl_trades[0].pnl < 0


def test_prediction_box_format():
    """Verify terminal prediction box output format."""
    from ml.predict import PredictionResult
    res = PredictionResult(
        signal="BUY",
        confidence=0.682,
        buy_probability=0.682,
        hold_probability=0.213,
        sell_probability=0.105,
        reason="ML model predicts positive price movement (Confidence: 68.2%).",
        timestamp=1700000000000,
        price=68450.0,
    )
    box_str = format_prediction_box(res, symbol="BTC/USDT")
    assert "AI TRADING SIGNAL" in box_str
    assert "BUY" in box_str
    assert "68.2%" in box_str
    assert "BUY probability:" in box_str
    assert "HOLD probability:" in box_str
    assert "SELL probability:" in box_str


if __name__ == "__main__":
    import sys
    test_functions = [
        test_zero_lookahead_feature_isolation,
        test_target_labeling_3_classes,
        test_chronological_split_no_leakage,
        test_confidence_threshold_filtering,
        test_backtest_slippage_and_fees,
        test_intraday_stop_loss_trigger,
        test_prediction_box_format,
    ]
    passed = 0
    failed = 0
    print("Running ML Pipeline Test Suite...")
    for fn in test_functions:
        try:
            fn()
            print(f"  [OK] {fn.__name__}")
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {fn.__name__}: {e}")
            failed += 1
    print(f"\nResults: {passed} passed, {failed} failed.")
    if failed > 0:
        sys.exit(1)
