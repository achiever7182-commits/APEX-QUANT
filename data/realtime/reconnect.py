"""
data/realtime/reconnect.py — Connection Lifecycle & Bounded Reconnect Engine.

Manages connection transitions, exponential backoff with ceiling limits,
bounded retries, and clean failure states.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from data.realtime.models import ConnectionState

logger = logging.getLogger("apex_quant.realtime.reconnect")


class ConnectionManager:
    """
    Coordinates connection state machine and backoff schedule.
    Prevents tight reconnect loops and enforces fail-closed bounded retry policy.
    """

    def __init__(
        self,
        max_attempts: int = 5,
        base_delay_seconds: float = 1.0,
        max_delay_seconds: float = 30.0,
        backoff_multiplier: float = 2.0,
        **kwargs,
    ):
        base_d = kwargs.get("base_delay", base_delay_seconds)
        max_d = kwargs.get("max_delay", max_delay_seconds)
        self.max_attempts: int = int(max_attempts)
        self.base_delay_seconds: float = float(base_d)
        self.max_delay_seconds: float = float(max_d)
        self.backoff_multiplier: float = float(backoff_multiplier)

        self.state: ConnectionState = ConnectionState.DISCONNECTED
        self.attempt_count: int = 0
        self.last_attempt_time: Optional[datetime] = None
        self.last_connected_time: Optional[datetime] = None

    def can_retry(self) -> bool:
        """Check if remaining retry attempts exist."""
        return self.attempt_count < self.max_attempts

    def increment_attempt(self) -> None:
        """Manually advance retry attempt counter."""
        self.attempt_count += 1
        self.last_attempt_time = datetime.now(timezone.utc)
        if not self.can_retry():
            self.state = ConnectionState.FAILED

    def compute_next_delay(self) -> float:
        """Calculate next backoff duration in seconds."""
        delay = self.base_delay_seconds * (self.backoff_multiplier ** self.attempt_count)
        return min(self.max_delay_seconds, delay)

    def record_connecting(self) -> None:
        """Transition into CONNECTING state."""
        self.state = ConnectionState.CONNECTING

    def record_success(self) -> None:
        """Transition into CONNECTED state and reset retry counters."""
        self.state = ConnectionState.CONNECTED
        self.attempt_count = 0
        self.last_connected_time = datetime.now(timezone.utc)
        logger.info("[ConnectionManager] Feed successfully connected.")

    def record_failure(self) -> float:
        """
        Record connection failure, advance retry counter, and compute required delay.
        Transitions to FAILED if maximum attempts are exhausted.
        """
        self.attempt_count += 1
        self.last_attempt_time = datetime.now(timezone.utc)

        if self.can_retry():
            self.state = ConnectionState.RECONNECTING
            delay = self.compute_next_delay()
            logger.warning(
                f"[ConnectionManager] Connection failure #{self.attempt_count}/{self.max_attempts}. "
                f"Backing off for {delay:.2f}s."
            )
            return delay
        else:
            self.state = ConnectionState.FAILED
            logger.error(
                f"[ConnectionManager] Reconnect attempts exhausted ({self.max_attempts}/{self.max_attempts}). "
                "State transitioned to FAILED."
            )
            return 0.0

    def record_disconnect(self) -> None:
        """Transition to DISCONNECTED upon intentional or unexpected disconnect."""
        self.state = ConnectionState.DISCONNECTED
        logger.info("[ConnectionManager] Feed disconnected.")

    def reset(self) -> None:
        """Reset manager back to initial clean state."""
        self.state = ConnectionState.DISCONNECTED
        self.attempt_count = 0
        self.last_attempt_time = None
