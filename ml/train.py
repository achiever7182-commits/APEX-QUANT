"""
ml/train.py — End-to-end model training, validation optimization, and test evaluation.

Usage:
    python ml/train.py --days 30 --timeframe 5m --symbol BTC/USDT
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# Add root directory to sys.path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import config
from core.strategies.ml_strategy import MLStrategy
from backtester.engine import BacktestEngine
from backtester.metrics import compute_metrics
from ml.data_loader import load_historical_data
from ml.dataset import create_ml_dataset, LABEL_SELL, LABEL_HOLD, LABEL_BUY
from ml.evaluate import evaluate_model, print_evaluation_report
from ml.model import MLModel
def run_strategy_backtest(
    model: MLModel,
    candles: list,
    min_confidence: float,
    symbol: str,
    timeframe: str,
    stop_loss: float = 0.015,
    take_profit: float = 0.035,
) -> dict:
    """Run an isolated backtest using MLStrategy and return metric dict."""
    if len(candles) < 50:
        return {}

    strategy = MLStrategy(
        model=model,
        min_confidence=min_confidence,
        stop_loss=stop_loss,
        take_profit=take_profit,
    )
    engine = BacktestEngine(
        starting_balance=10_000.0,
        fee_rate=0.001,
        slippage_pct=getattr(config, "SLIPPAGE", 0.0005),
        symbol=symbol,
        timeframe=timeframe,
    )
    result = engine.run(strategy, candles)
    m = compute_metrics(result)
    return {
        "trade_count": m.trade_count,
        "win_count": m.win_count,
        "loss_count": m.loss_count,
        "win_rate_pct": m.win_rate_pct,
        "profit_factor": m.profit_factor if m.profit_factor != float("inf") else 999.0,
        "total_return_pct": m.total_return_pct,
        "max_drawdown_pct": m.max_drawdown_pct,
        "sharpe_ratio": m.sharpe_ratio,
    }


def train_pipeline(
    symbol: str = "BTC/USDT",
    timeframe: str = "1h",
    days: int = 730,
    horizon: int = 4,
    buy_threshold: float = 0.010,
    sell_threshold: float = -0.010,
    min_confidence: float = 0.50,
    stop_loss: float = 0.015,
    take_profit: float = 0.035,
    output_path: str = "models/ml_model.joblib",
    tune_confidence: bool = True,
    force_download: bool = False,
) -> tuple[MLModel, dict]:
    console = Console()

    console.print()
    banner = Panel.fit(
        "[bold cyan]AUTONOMOUS ML TRADING PIPELINE — 2-YEAR HISTORICAL TRAINING[/bold cyan]\n"
        "[dim]RandomForest Classifier • 3-Class Conviction • 2.3:1 Risk-Reward • Zero-Lookahead[/dim]",
        border_style="cyan",
    )
    console.print(banner)
    console.print()

    # 1. Load Historical Data
    console.print(f"[bold]Step 1:[/bold] Loading historical data for [cyan]{symbol}[/cyan] ({timeframe}, past {days} days)...")
    candles = load_historical_data(symbol=symbol, timeframe=timeframe, days=days, force_download=force_download)
    console.print(f"[green][OK][/green] Loaded [bold]{len(candles):,}[/bold] historical candles.")

    if len(candles) < 150:
        raise ValueError(f"Insufficient candles loaded ({len(candles)}). Need at least 150 for ML dataset.")

    # 2. Extract Features & Create Chronological Split
    console.print(f"[bold]Step 2:[/bold] Engineering 20 features (horizon={horizon} bars, buy_thresh=+{buy_threshold*100:.1f}%, sell_thresh={sell_threshold*100:.1f}%)...")
    ds = create_ml_dataset(
        candles=candles,
        horizon=horizon,
        buy_threshold=buy_threshold,
        sell_threshold=sell_threshold,
        train_ratio=0.70,
        val_ratio=0.15,
    )

    # Display dataset breakdown
    t_ds = Table(box=box.SIMPLE_HEAVY, title="Dataset Chronological Split Breakdown")
    t_ds.add_column("Split", style="bold")
    t_ds.add_column("Samples", justify="right")
    t_ds.add_column("SELL (0)", justify="right")
    t_ds.add_column("HOLD (1)", justify="right")
    t_ds.add_column("BUY (2)", justify="right")

    for split_name, y_arr in [("Train (70%)", ds.y_train), ("Val (15%)", ds.y_val), ("Test (15%)", ds.y_test)]:
        n_s = int((y_arr == LABEL_SELL).sum())
        n_h = int((y_arr == LABEL_HOLD).sum())
        n_b = int((y_arr == LABEL_BUY).sum())
        tot = len(y_arr)
        t_ds.add_row(
            split_name,
            f"{tot:,}",
            f"{n_s} ({n_s / max(tot, 1) * 100:.1f}%)",
            f"{n_h} ({n_h / max(tot, 1) * 100:.1f}%)",
            f"{n_b} ({n_b / max(tot, 1) * 100:.1f}%)",
        )
    console.print(t_ds)
    console.print()

    # 3. Train Model
    console.print("[bold]Step 3:[/bold] Training Random Forest model with 160 estimators (depth=8, balanced weights)...")
    model = MLModel(
        feature_names=ds.feature_names,
        min_confidence=min_confidence,
        n_estimators=160,
        max_depth=7,
        min_samples_leaf=25,
        random_state=42,
    )
    model.fit(ds.X_train, ds.y_train)
    console.print("[green][OK][/green] Model training completed successfully.")

    # 4. Tune Confidence Threshold on Validation Set
    best_conf = min_confidence
    if tune_confidence and len(ds.val_candles) > 50:
        console.print(f"\n[bold]Step 4:[/bold] Optimizing confidence threshold on [yellow]Validation Set[/yellow] (SL: {stop_loss*100:.1f}%, TP: {take_profit*100:.1f}%)...")
        candidates = [0.48, 0.50, 0.52, 0.55]
        best_score = -9999.0

        t_tune = Table(box=box.ROUNDED, title="Validation Set Threshold Tuning")
        t_tune.add_column("Confidence Threshold", justify="center")
        t_tune.add_column("Trades", justify="right")
        t_tune.add_column("Win Rate", justify="right")
        t_tune.add_column("Net Return", justify="right")
        t_tune.add_column("Profit Factor", justify="right")

        for c_cand in candidates:
            cand_res = run_strategy_backtest(
                model=model,
                candles=ds.val_candles,
                min_confidence=c_cand,
                symbol=symbol,
                timeframe=timeframe,
                stop_loss=stop_loss,
                take_profit=take_profit,
            )
            trades = cand_res.get("trade_count", 0)
            wr = cand_res.get("win_rate_pct", 0.0)
            ret = cand_res.get("total_return_pct", 0.0)
            pf = cand_res.get("profit_factor", 0.0)
            t_tune.add_row(f"{c_cand * 100:.0f}%", str(trades), f"{wr:.1f}%", f"{ret:+.2f}%", f"{pf:.2f}")

            # Profitability objective: prioritizes positive return and healthy profit factor
            if ret > 0 and trades >= 2:
                score = (ret * 5.0) + (min(pf, 10.0) * 3.0) + (wr * 0.1)
            else:
                score = -100.0 + ret

            if score > best_score:
                best_score = score
                best_conf = c_cand

        console.print(t_tune)
        console.print(f"[bold cyan]Selected Optimal Confidence Threshold:[/bold cyan] [bold green]{best_conf * 100:.0f}%[/bold green]")
        model.min_confidence = best_conf

    # 5. Evaluate on Validation Set
    val_eval = evaluate_model(model, ds.X_val, ds.y_val)
    val_trading = run_strategy_backtest(
        model=model,
        candles=ds.val_candles,
        min_confidence=model.min_confidence,
        symbol=symbol,
        timeframe=timeframe,
        stop_loss=stop_loss,
        take_profit=take_profit,
    )
    print_evaluation_report(val_eval, val_trading, dataset_name="VALIDATION SET")

    # 6. Evaluate Once on Test Set (Strictly Untouched Data)
    test_eval = evaluate_model(model, ds.X_test, ds.y_test)
    test_trading = run_strategy_backtest(
        model=model,
        candles=ds.test_candles,
        min_confidence=model.min_confidence,
        symbol=symbol,
        timeframe=timeframe,
        stop_loss=stop_loss,
        take_profit=take_profit,
    )
    print_evaluation_report(test_eval, test_trading, dataset_name="TEST SET (UNTOUCHED UNSEEN DATA)")

    # 7. Serialize Model & Metadata
    metadata = {
        "model_type": "RandomForestClassifier",
        "symbol": symbol,
        "timeframe": timeframe,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "horizon": horizon,
        "buy_threshold": buy_threshold,
        "sell_threshold": sell_threshold,
        "min_confidence": model.min_confidence,
        "stop_loss_pct": stop_loss,
        "take_profit_pct": take_profit,
        "feature_names": ds.feature_names,
        "sample_counts": {
            "total_candles": len(candles),
            "train_samples": len(ds.y_train),
            "val_samples": len(ds.y_val),
            "test_samples": len(ds.y_test),
        },
        "validation_metrics": {
            "accuracy": val_eval.get("accuracy", 0.0),
            "precision": val_eval.get("precision_weighted", 0.0),
            "f1": val_eval.get("f1_weighted", 0.0),
            "trading": val_trading,
        },
        "test_metrics": {
            "accuracy": test_eval.get("accuracy", 0.0),
            "precision": test_eval.get("precision_weighted", 0.0),
            "f1": test_eval.get("f1_weighted", 0.0),
            "trading": test_trading,
        },
        "disclaimer": (
            "This model is a research prototype. Machine learning predictions are probabilistic "
            "and do not guarantee profits. Past backtest results do not predict future performance."
        ),
    }

    model.save(output_path, metadata=metadata)
    console.print(f"[bold green][OK] Model successfully saved to:[/bold green] [cyan]{output_path}[/cyan]")
    console.print(f"[bold green][OK] Metadata saved to:[/bold green] [cyan]{os.path.splitext(output_path)[0]}_metadata.json[/cyan]")
    console.print()

    return model, metadata


def main() -> None:
    parser = argparse.ArgumentParser(description="Train Autonomous ML Trading Model")
    parser.add_argument("--symbol", type=str, default=getattr(config, "ML_SYMBOL", "BTC/USDT"), help="Trading pair")
    parser.add_argument("--timeframe", type=str, default="1h", help="Candle timeframe (default: 1h)")
    parser.add_argument("--days", type=int, default=730, help="Days of historical data (default: 730 = 2 years)")
    parser.add_argument("--horizon", type=int, default=4, help="Prediction lookahead bars (default: 4)")
    parser.add_argument("--buy-threshold", type=float, default=0.010, help="Min return for BUY (default: 0.010 = 1.0%%)")
    parser.add_argument("--sell-threshold", type=float, default=-0.010, help="Max return for SELL (default: -0.010 = -1.0%%)")
    parser.add_argument("--confidence", type=float, default=0.50, help="Minimum prediction confidence (default: 0.50)")
    parser.add_argument("--stop-loss", type=float, default=0.015, help="Stop loss pct (default: 0.015 = 1.5%%)")
    parser.add_argument("--take-profit", type=float, default=0.035, help="Take profit pct (default: 0.035 = 3.5%%)")
    parser.add_argument("--output", type=str, default=getattr(config, "ML_MODEL_PATH", "models/ml_model.joblib"), help="Path to save model")
    parser.add_argument("--no-tune", action="store_true", help="Skip confidence threshold tuning")
    parser.add_argument("--force-download", action="store_true", help="Force fresh download from Binance API")

    args = parser.parse_args()

    train_pipeline(
        symbol=args.symbol,
        timeframe=args.timeframe,
        days=args.days,
        horizon=args.horizon,
        buy_threshold=args.buy_threshold,
        sell_threshold=args.sell_threshold,
        min_confidence=args.confidence,
        stop_loss=args.stop_loss,
        take_profit=args.take_profit,
        output_path=args.output,
        tune_confidence=not args.no_tune,
        force_download=args.force_download,
    )


if __name__ == "__main__":
    main()
