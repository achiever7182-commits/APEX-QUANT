"""
risk/kill_switch.py — Persistent Emergency Kill Switch for Paper Trading.

Guarantees:
  1. Instant order rejection when active.
  2. Persistent across process restarts (saved to disk atomically).
  3. Market data, accounting, logging, and reconciliation continue uninterrupted.
  4. Does NOT automatically liquidate positions unless explicitly instructed.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional


@dataclass
class KillSwitchState:
    """State record for the persistent kill switch."""
    is_active: bool = False
    reason: Optional[str] = None
    enabled_at: Optional[str] = None
    disabled_at: Optional[str] = None
    operator: str = "SYSTEM"


class PersistentKillSwitch:
    """Manages disk-backed persistent kill switch state."""

    def __init__(self, persistence_path: str = "data/paper/kill_switch.json"):
        self.persistence_path: str = persistence_path
        self.state: KillSwitchState = KillSwitchState()
        self._load_state()

    def _load_state(self) -> None:
        """Load state from disk if available."""
        if os.path.exists(self.persistence_path):
            try:
                with open(self.persistence_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.state = KillSwitchState(
                        is_active=bool(data.get("is_active", False)),
                        reason=data.get("reason"),
                        enabled_at=data.get("enabled_at"),
                        disabled_at=data.get("disabled_at"),
                        operator=data.get("operator", "SYSTEM"),
                    )
            except Exception as e:
                # If corrupted, preserve state as active for safety
                self.state = KillSwitchState(
                    is_active=True,
                    reason=f"CORRUPTED_PERSISTENCE: {str(e)}",
                    enabled_at=datetime.now(timezone.utc).isoformat(),
                    operator="RECOVERY",
                )

    def _save_state(self) -> None:
        """Persist state atomically to disk."""
        os.makedirs(os.path.dirname(os.path.abspath(self.persistence_path)), exist_ok=True)
        dir_name = os.path.dirname(os.path.abspath(self.persistence_path))

        with tempfile.NamedTemporaryFile("w", dir=dir_name, delete=False, encoding="utf-8") as tf:
            json.dump(asdict(self.state), tf, indent=2)
            temp_name = tf.name

        os.replace(temp_name, os.path.abspath(self.persistence_path))

    def is_active(self) -> bool:
        """Check if kill switch is currently engaged."""
        return self.state.is_active

    def enable(self, reason: str = "MANUAL_OPERATOR_TRIGGER", operator: str = "OPERATOR") -> None:
        """Engage the kill switch. All new orders will be rejected."""
        self.state.is_active = True
        self.state.reason = reason
        self.state.enabled_at = datetime.now(timezone.utc).isoformat()
        self.state.operator = operator
        self._save_state()

    def disable(self, operator: str = "OPERATOR") -> None:
        """Disengage the kill switch. New orders can be evaluated."""
        self.state.is_active = False
        self.state.disabled_at = datetime.now(timezone.utc).isoformat()
        self.state.operator = operator
        self._save_state()

    def get_status(self) -> Dict[str, Any]:
        """Get summary status dict."""
        return asdict(self.state)
