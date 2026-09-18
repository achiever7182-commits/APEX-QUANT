"""
Centralized Configuration for Real-Time Indian Market Data Infrastructure.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class RealtimeConfig:
    """
    Configuration parameters for real-time market data ingestion.
    """
    provider_name: str = "mock"
    max_staleness_seconds: float = 300.0
    reconnect_base_delay: float = 1.0
    reconnect_max_delay: float = 30.0
    reconnect_max_attempts: int = 5
    bar_interval_seconds: int = 300  # 5-minute bars
    clock_skew_tolerance_seconds: float = 5.0
    default_symbols: List[str] = field(default_factory=lambda: [
        "NSE:RELIANCE",
        "NSE:TCS",
        "NSE:INFY",
        "NSE:HDFCBANK",
        "NSE:ICICIBANK",
    ])
    max_buffer_size: int = 500
    mock_seed: int = 42


# Global configuration constants
REALTIME_PROVIDER = os.getenv("APEX_REALTIME_PROVIDER", "mock")
REALTIME_MAX_STALENESS_SECONDS = float(os.getenv("APEX_REALTIME_MAX_STALENESS_SECONDS", "300.0"))
REALTIME_RECONNECT_BASE_DELAY = float(os.getenv("APEX_REALTIME_RECONNECT_BASE_DELAY", "1.0"))
REALTIME_RECONNECT_MAX_DELAY = float(os.getenv("APEX_REALTIME_RECONNECT_MAX_DELAY", "30.0"))
REALTIME_RECONNECT_MAX_ATTEMPTS = int(os.getenv("APEX_REALTIME_RECONNECT_MAX_ATTEMPTS", "5"))
REALTIME_BAR_INTERVAL_SECONDS = int(os.getenv("APEX_REALTIME_BAR_INTERVAL_SECONDS", "300"))
REALTIME_CLOCK_SKEW_TOLERANCE_SECONDS = float(os.getenv("APEX_REALTIME_CLOCK_SKEW_TOLERANCE_SECONDS", "5.0"))

DEFAULT_REALTIME_SYMBOLS = [
    "NSE:RELIANCE",
    "NSE:TCS",
    "NSE:INFY",
    "NSE:HDFCBANK",
    "NSE:ICICIBANK",
]
