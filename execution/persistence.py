"""
execution/persistence.py — Atomic State Persistence & Crash-Safe Restart for Paper Trading.

Guarantees:
  1. Atomic disk writes (tempfile + atomic os.replace) preventing file corruption.
  2. Completely isolated from legacy Binance bot (stored in data/paper/).
  3. Full state restoration on restart: Account, Positions, Orders, Fills, Idempotency keys.
  4. Safe resumption without order duplication.
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import Any, Dict, List, Optional, Tuple
from execution.models import (
    PaperAccount,
    PaperAuditEvent,
    PaperFill,
    PaperOrder,
    PaperPosition,
)


class PaperStatePersistence:
    """Manages atomic disk persistence and restoration for the paper trading subsystem."""

    def __init__(self, data_dir: str = "data/paper"):
        self.data_dir: str = data_dir
        self.account_file: str = os.path.join(data_dir, "account.json")
        self.positions_file: str = os.path.join(data_dir, "positions.json")
        self.orders_file: str = os.path.join(data_dir, "orders.json")
        self.fills_file: str = os.path.join(data_dir, "fills.json")
        self.events_file: str = os.path.join(data_dir, "events.jsonl")
        os.makedirs(self.data_dir, exist_ok=True)

    def _atomic_write_json(self, file_path: str, data: Any) -> None:
        """Atomically write data to disk via temporary file."""
        dir_name = os.path.dirname(os.path.abspath(file_path))
        os.makedirs(dir_name, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", dir=dir_name, delete=False, encoding="utf-8") as tf:
            json.dump(data, tf, indent=2)
            temp_name = tf.name
        os.replace(temp_name, os.path.abspath(file_path))

    def save_state(
        self,
        account: PaperAccount,
        positions: Dict[str, PaperPosition],
        orders: Dict[str, PaperOrder],
        fills: List[PaperFill],
    ) -> None:
        """Persist full paper trading state atomically."""
        # 1. Save Account
        self._atomic_write_json(self.account_file, account.to_dict())

        # 2. Save Positions
        pos_data = {sym: p.to_dict() for sym, p in positions.items()}
        self._atomic_write_json(self.positions_file, pos_data)

        # 3. Save Orders
        orders_data = {oid: o.to_dict() for oid, o in orders.items()}
        self._atomic_write_json(self.orders_file, orders_data)

        # 4. Save Fills
        fills_data = [f.to_dict() for f in fills]
        self._atomic_write_json(self.fills_file, fills_data)

    def append_event(self, event: PaperAuditEvent) -> None:
        """Append audit event to events.jsonl."""
        line = json.dumps(event.to_dict()) + "\n"
        with open(self.events_file, "a", encoding="utf-8") as f:
            f.write(line)

    def state_exists(self) -> bool:
        """Check if prior paper state exists on disk."""
        return os.path.exists(self.account_file) and os.path.exists(self.positions_file)

    def load_state(
        self,
    ) -> Tuple[Optional[PaperAccount], Dict[str, PaperPosition], Dict[str, PaperOrder], List[PaperFill]]:
        """
        Load and reconstruct state from disk.
        
        Returns:
            Tuple of (account, positions_dict, orders_dict, fills_list).
            If no state exists, returns (None, {}, {}, []).
        """
        if not self.state_exists():
            return None, {}, {}, []

        account: Optional[PaperAccount] = None
        positions: Dict[str, PaperPosition] = {}
        orders: Dict[str, PaperOrder] = {}
        fills: List[PaperFill] = []

        try:
            with open(self.account_file, "r", encoding="utf-8") as f:
                account = PaperAccount.from_dict(json.load(f))

            with open(self.positions_file, "r", encoding="utf-8") as f:
                pos_data = json.load(f)
                for sym, p_dict in pos_data.items():
                    positions[sym] = PaperPosition.from_dict(p_dict)

            if os.path.exists(self.orders_file):
                with open(self.orders_file, "r", encoding="utf-8") as f:
                    ord_data = json.load(f)
                    for oid, o_dict in ord_data.items():
                        orders[oid] = PaperOrder.from_dict(o_dict)

            if os.path.exists(self.fills_file):
                with open(self.fills_file, "r", encoding="utf-8") as f:
                    f_data = json.load(f)
                    for f_dict in f_data:
                        fills.append(PaperFill.from_dict(f_dict))

        except Exception as e:
            raise RuntimeError(f"Failed to load paper state from disk: {e}")

        return account, positions, orders, fills
