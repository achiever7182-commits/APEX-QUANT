import json
import csv
from datetime import datetime
from config import MIN_SECONDS_BETWEEN_TRADES

print(f"Configured min_seconds_between_trades: {MIN_SECONDS_BETWEEN_TRADES}s")

# 1. Verify bot_state.json
with open("bot_state.json") as f:
    state = json.load(f)

print("\n--- VERIFYING BOT_STATE.JSON TRADE HISTORY ---")
for i, t in enumerate(state.get("trade_history", []), 1):
    fmt = "%Y-%m-%d %H:%M:%S.%f"
    t_entry = datetime.strptime(t["entry_time"], fmt)
    t_exit = datetime.strptime(t["exit_time"], fmt)
    diff = (t_exit - t_entry).total_seconds()
    print(f"Trade #{i}:")
    print(f"  BUY  timestamp : {t['entry_time']} (Order {t.get('entry_order_id')})")
    print(f"  SELL timestamp : {t['exit_time']} (Order {t.get('exit_order_id')})")
    print(f"  Elapsed delta  : {diff:,.3f} seconds")
    assert diff >= MIN_SECONDS_BETWEEN_TRADES, f"Delta {diff} < {MIN_SECONDS_BETWEEN_TRADES}"
    print(f"  Assertion passed: {diff:.3f}s >= {MIN_SECONDS_BETWEEN_TRADES}s")

# 2. Verify trade_log.csv paired lines
print("\n--- VERIFYING TRADE_LOG.CSV PAIRED ACTIONS ---")
with open("trade_log.csv") as f:
    rows = list(csv.DictReader(f))

for i in range(0, len(rows) - 1, 2):
    r_buy = rows[i]
    r_sell = rows[i + 1]
    if r_buy["action"] == "BUY" and r_sell["action"] == "SELL":
        fmt = "%Y-%m-%d %H:%M:%S.%f"
        dt_buy = datetime.strptime(r_buy["timestamp"], fmt)
        dt_sell = datetime.strptime(r_sell["timestamp"], fmt)
        diff = (dt_sell - dt_buy).total_seconds()
        print(f"Pair {i // 2 + 1}:")
        print(f"  BUY  timestamp : {r_buy['timestamp']}")
        print(f"  SELL timestamp : {r_sell['timestamp']}")
        print(f"  Elapsed delta  : {diff:,.3f} seconds")
        assert diff >= MIN_SECONDS_BETWEEN_TRADES, f"Delta {diff} < {MIN_SECONDS_BETWEEN_TRADES}"
        print(f"  Assertion passed: {diff:.3f}s >= {MIN_SECONDS_BETWEEN_TRADES}s")
