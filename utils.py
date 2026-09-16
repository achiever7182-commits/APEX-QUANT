"""
utils.py — Shared helper functions used by all Python entry points.

Consolidates the duplicated readable_time / now_str / order_fill_price /
log_trade / timestamp helpers that were previously copy-pasted in every
main*.py file.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from config import LOG_FILE


# ---------------------------------------------------------------------------
# Time formatting
# ---------------------------------------------------------------------------

def readable_time(ms_timestamp: int) -> str:
    """Convert an exchange millisecond timestamp into a readable local time string."""
    return datetime.fromtimestamp(ms_timestamp / 1000).strftime("%Y-%m-%d %H:%M:%S")


def now_str(milliseconds: bool = False) -> str:
    """Current local time string.

    Args:
        milliseconds: If True, include milliseconds (HH:MM:SS.mmm).
                      If False, return YYYY-MM-DD HH:MM:SS.
    """
    if milliseconds:
        value = datetime.now().strftime("%H:%M:%S.%f")
        return value[:-3]  # trim microseconds to milliseconds
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def timestamp(microseconds: bool = True) -> str:
    """High-precision timestamp for the terminal-live dashboard.

    Args:
        microseconds: If True, includes full microseconds.
                      If False, trims to milliseconds.
    """
    value = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    return value if microseconds else value[:-3]


# ---------------------------------------------------------------------------
# Order helpers
# ---------------------------------------------------------------------------

def order_fill_price(order: dict[str, Any], fallback: float) -> float:
    """Extract the best fill-price estimate from a CCXT order response.

    Tries ``average``, then ``price``, then computes from ``cost / filled``.
    Falls back to *fallback* if nothing is available.
    """
    average = order.get("average") or order.get("price")
    if average:
        return float(average)
    filled = float(order.get("filled") or 0.0)
    cost = float(order.get("cost") or 0.0)
    return cost / filled if filled else fallback


# ---------------------------------------------------------------------------
# Trade logging
# ---------------------------------------------------------------------------

def log_trade(
    action: str,
    ts: str,
    price: float,
    size: float,
    pnl: float | None = None,
    confidence: float | None = None,
    reason: str = "",
) -> None:
    """Append a trade action to the CSV log file."""
    file_exists = os.path.isfile(LOG_FILE)
    pnl_str = f"{pnl:+.4f}" if pnl is not None else ""
    conf_str = f"{confidence * 100:.1f}%" if confidence is not None and confidence > 0 else ""
    clean_reason = reason.replace('"', "'").replace("\n", " ")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        if not file_exists or os.path.getsize(LOG_FILE) == 0:
            f.write("timestamp,action,price,size,pnl,confidence,reason\n")
        f.write(f"{ts},{action},{price:.2f},{size:.6f},{pnl_str},{conf_str},\"{clean_reason}\"\n")
