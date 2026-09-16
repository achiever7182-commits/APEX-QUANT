"""
ml/evaluate.py — Model classification evaluation metrics and performance comparisons.

Separates statistical machine-learning metrics (Accuracy, Precision, Recall, F1, Confusion Matrix)
from actual portfolio trading performance (Win Rate, Profit Factor, Return, Max Drawdown).
"""

from __future__ import annotations

from typing import Any
import sys
import numpy as np
from sklearn.metrics import accuracy_score, precision_recall_fscore_support, confusion_matrix

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from rich import box
from rich.console import Console
from rich.table import Table
from rich.text import Text

from ml.dataset import LABEL_BUY, LABEL_HOLD, LABEL_SELL


def evaluate_model(model: Any, X: np.ndarray, y: np.ndarray) -> dict[str, Any]:
    """Calculate accuracy, precision, recall, f1, and confusion matrix."""
    if len(X) == 0:
        return {}

    # Get predictions
    proba = model.predict_proba(X)
    y_pred = np.argmax(proba, axis=1)

    acc = float(accuracy_score(y, y_pred))
    p, r, f1, _ = precision_recall_fscore_support(
        y, y_pred, average="weighted", zero_division=0
    )
    cm = confusion_matrix(y, y_pred, labels=[LABEL_SELL, LABEL_HOLD, LABEL_BUY])

    # Per-class metrics
    p_per, r_per, f_per, sup = precision_recall_fscore_support(
        y, y_pred, labels=[LABEL_SELL, LABEL_HOLD, LABEL_BUY], zero_division=0
    )

    return {
        "accuracy": acc,
        "precision_weighted": float(p),
        "recall_weighted": float(r),
        "f1_weighted": float(f1),
        "confusion_matrix": cm,
        "class_metrics": {
            "SELL": {"precision": float(p_per[0]), "recall": float(r_per[0]), "f1": float(f_per[0]), "support": int(sup[0])},
            "HOLD": {"precision": float(p_per[1]), "recall": float(r_per[1]), "f1": float(f_per[1]), "support": int(sup[1])},
            "BUY":  {"precision": float(p_per[2]), "recall": float(r_per[2]), "f1": float(f_per[2]), "support": int(sup[2])},
        },
    }


def print_evaluation_report(
    eval_metrics: dict[str, Any],
    trading_metrics: dict[str, Any] | None = None,
    dataset_name: str = "VALIDATION SET",
) -> None:
    """Print clean comparison of statistical ML metrics vs trading metrics."""
    console = Console()

    console.print()
    header = Text(f"  {dataset_name.upper()} — MODEL EVALUATION & TRADING METRICS  ", style="bold white on dark_blue")
    console.print(header)
    console.print()

    # 1. Statistical ML Metrics
    t1 = Table(box=box.ROUNDED, border_style="cyan", title="[bold]1. Statistical Machine Learning Metrics[/bold]", title_justify="left")
    t1.add_column("Metric", style="bright_black", min_width=25)
    t1.add_column("Score", justify="right", min_width=18)
    t1.add_column("Description", style="white", min_width=30)

    acc = eval_metrics.get("accuracy", 0.0) * 100.0
    prec = eval_metrics.get("precision_weighted", 0.0) * 100.0
    rec = eval_metrics.get("recall_weighted", 0.0) * 100.0
    f1 = eval_metrics.get("f1_weighted", 0.0) * 100.0

    t1.add_row("Accuracy", f"{acc:.2f}%", "Overall correct 3-class predictions")
    t1.add_row("Weighted Precision", f"{prec:.2f}%", "True positives over predicted positives")
    t1.add_row("Weighted Recall", f"{rec:.2f}%", "True positives over actual positives")
    t1.add_row("Weighted F1 Score", f"{f1:.2f}%", "Harmonic balance of precision and recall")

    console.print(t1)

    # 2. Confusion Matrix
    cm = eval_metrics.get("confusion_matrix")
    if cm is not None and len(cm) == 3:
        t_cm = Table(box=box.ROUNDED, border_style="blue", title="[bold]2. 3-Class Confusion Matrix[/bold]", title_justify="left")
        t_cm.add_column("Actual \\ Predicted", style="bold magenta", justify="left")
        t_cm.add_column("Pred SELL (0)", justify="right")
        t_cm.add_column("Pred HOLD (1)", justify="right")
        t_cm.add_column("Pred BUY (2)", justify="right")

        t_cm.add_row("Actual SELL", str(cm[0][0]), str(cm[0][1]), str(cm[0][2]))
        t_cm.add_row("Actual HOLD", str(cm[1][0]), str(cm[1][1]), str(cm[1][2]))
        t_cm.add_row("Actual BUY", str(cm[2][0]), str(cm[2][1]), str(cm[2][2]))
        console.print(t_cm)

    # 3. Trading Metrics (if available)
    if trading_metrics:
        t2 = Table(box=box.ROUNDED, border_style="green", title="[bold]3. Simulated Trading Performance (Backtest Result)[/bold]", title_justify="left")
        t2.add_column("Trading Metric", style="bright_black", min_width=25)
        t2.add_column("Value", justify="right", min_width=18)

        wr = trading_metrics.get("win_rate_pct", 0.0)
        pf = trading_metrics.get("profit_factor", 0.0)
        ret = trading_metrics.get("total_return_pct", 0.0)
        mdd = trading_metrics.get("max_drawdown_pct", 0.0)
        trades = trading_metrics.get("trade_count", 0)

        t2.add_row("Total Trades", str(trades))
        t2.add_row("Trading Win Rate", f"{wr:.2f}%")
        t2.add_row("Profit Factor", f"{pf:.4f}")
        t2.add_row("Net Portfolio Return", f"{ret:+.2f}%")
        t2.add_row("Max Drawdown", f"{mdd:.2f}%")
        console.print(t2)

    console.print(Text("  NOTE: Model Accuracy != Trading Profitability. High accuracy on neutral HOLD does not guarantee profit.", style="italic bright_black"))
    console.print()
