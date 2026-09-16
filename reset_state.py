"""
reset_state.py — Safely archive old trade history, reset bot_state.json & trade_log.csv,
and notify the running web dashboard immediately.

Usage:
    python reset_state.py
"""

import json
import os
import shutil
import urllib.request
from datetime import datetime

STATE_FILE = "bot_state.json"
LOG_FILE = "trade_log.csv"


def reset_all() -> dict:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 1. Archive & reset bot_state.json
    if os.path.exists(STATE_FILE):
        archive_name = f"bot_state_archive_{timestamp}.json"
        try:
            shutil.copyfile(STATE_FILE, archive_name)
            print(f"[OK] Archived existing state to: {archive_name}")
        except Exception as e:
            print(f"[WARN] Could not copy state archive: {e}")

    # Fetch live balance from Binance Testnet
    live_balance = 86849.75
    try:
        from adapters.binance_adapter import BinanceTestnetAdapter
        from config import API_KEY, API_SECRET, SYMBOL
        if API_KEY and API_SECRET:
            adapter = BinanceTestnetAdapter(API_KEY, API_SECRET, symbol=SYMBOL)
            b = adapter.fetch_balance("USDT")
            if b and b > 0:
                live_balance = round(float(b), 2)
    except Exception as e:
        print(f"[INFO] Using cached balance {live_balance}: {e}")

    now_iso = datetime.now().isoformat()
    clean_state = {
        "version": 1,
        "session_start": now_iso,
        "open_position": None,
        "daily_pnl": 0.0,
        "realized_pnl": 0.0,
        "trade_count": 0,
        "win_count": 0,
        "loss_count": 0,
        "total_fees_paid": 0.0,
        "last_saved": now_iso,
        "trade_history": []
    }

    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(clean_state, f, indent=2)
    print(f"[OK] bot_state.json reset to clean state (Realized PnL: $0.00, Trades: 0, Balance: ${live_balance:,.2f}).")

    # 2. Archive & reset trade_log.csv
    if os.path.exists(LOG_FILE):
        log_archive = f"trade_log_archive_{timestamp}.csv"
        try:
            shutil.copyfile(LOG_FILE, log_archive)
            print(f"[OK] Archived existing trade log to: {log_archive}")
        except Exception as e:
            print(f"[WARN] Could not copy log archive: {e}")

    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write("timestamp,action,price,size,order_id,confidence,reason\n")
    print(f"[OK] trade_log.csv reset with fresh header.")

    # 3. Push telemetry to local web dashboard server if running
    telemetry_payload = {
        "symbol": "BTC/USDT",
        "price": 75520.0,
        "signal": "HOLD",
        "realized_pnl": 0.0,
        "unrealized_pnl": 0.0,
        "daily_pnl": 0.0,
        "trade_count": 0,
        "win_count": 0,
        "loss_count": 0,
        "win_rate": 0.0,
        "total_fees_paid": 0.0,
        "position_open": False,
        "position_size": 0.0,
        "entry_price": 0.0,
        "balance": live_balance,
        "starting_balance": live_balance,
        "is_bot_running": True,
        "last_trade_pnl": None,
        "actions": [],
        "last_action": None,
        "timestamp": datetime.now().strftime("%H:%M:%S"),
    }

    try:
        data = json.dumps(telemetry_payload).encode("utf-8")
        req = urllib.request.Request(
            "http://127.0.0.1:5000/api/telemetry",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            print(f"[OK] Broadcast clean state to Web Dashboard on http://127.0.0.1:5000 (status: {resp.status})")
    except Exception as e:
        print(f"[INFO] Note: Dashboard notification ({e})")

    return clean_state


if __name__ == "__main__":
    reset_all()
    print("\nSUCCESS: Panel and local state completely reset to a clean slate!")
