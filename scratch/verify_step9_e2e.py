"""
scratch/verify_step9_e2e.py — End-to-End Controlled Paper Execution Verification.

Traces:
  Market Data -> Signal -> Risk Check -> Order -> Fill -> Accounting -> Position -> P&L -> Persistence -> Restart -> Reconciliation
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import pandas as pd

ROOT_DIR = r"c:\Users\achie\OneDrive\Desktop\Trading-Bot"
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from data.market.storage import ParquetMarketDataStorage
from features.engine import FeatureEngine
from execution.paper_engine import PaperTradingEngine
from execution.models import OrderStatus, ReconciliationStatus, PaperOrder, RejectionReason


def run_e2e_verification():
    print("=" * 100)
    print("APEX QUANT — STEP 9: END-TO-END PAPER EXECUTION & AUDIT VERIFICATION")
    print("=" * 100)
    print("ISOLATION GUARANTEE:")
    print("  • Simulated Broker Only : PaperBroker (Local execution simulation)")
    print("  • Real Broker Connected : ZERO (No broker, no API keys, no network orders)")
    print("  • Real Money Used       : ZERO (Virtual capital: ₹10,00,000.00)")
    print("  • Legacy Binance Bot    : UNTOUCHED (Zero interaction with bot_state.json)")
    print("=" * 100)

    test_data_dir = os.path.join(ROOT_DIR, "scratch", "paper_e2e_state")
    shutil.rmtree(test_data_dir, ignore_errors=True)
    os.makedirs(test_data_dir, exist_ok=True)

    storage = ParquetMarketDataStorage()
    symbols = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]

    # 1. Market Data Ingestion
    print("\n[STEP 1] MARKET DATA INGESTION:")
    engine_feat = FeatureEngine()
    feature_set = engine_feat.generate_panel_from_storage(
        storage=storage,
        symbols=symbols,
        start_date="2023-01-01",
        end_date="2024-04-15",
        is_adjusted=True,
    )
    panel = feature_set.data

    # Attach close prices to panel
    price_dfs = []
    for s in symbols:
        raw_df = storage.query_by_symbol(s, is_adjusted=True)
        price_dfs.append(raw_df[["timestamp", "symbol", "close"]])
    prices_all = pd.concat(price_dfs, ignore_index=True)
    panel = panel.merge(prices_all, on=["timestamp", "symbol"], how="left")

    # Get quotes at decision date T (2024-04-15)
    t_decision = pd.to_datetime("2024-04-15", utc=True)
    bar_dfs = {s: storage.query_by_symbol(s, is_adjusted=True) for s in symbols}

    current_quotes = {}
    current_volumes = {}
    for s in symbols:
        df_s = bar_dfs[s]
        row_t = df_s[pd.to_datetime(df_s["timestamp"]) == t_decision]
        if not row_t.empty:
            current_quotes[s] = float(row_t["close"].iloc[0])
            current_volumes[s] = float(row_t["volume"].iloc[0])
        else:
            current_quotes[s] = float(df_s["close"].iloc[-1])
            current_volumes[s] = float(df_s["volume"].iloc[-1])

    for s in symbols:
        print(f"  • {s:<10} | Decision Close Price: ₹{current_quotes[s]:8.2f} | Volume: {current_volumes[s]:10,.0f}")

    # 2. Initialize Paper Trading Engine
    print("\n[STEP 2] PAPER TRADING ENGINE INITIALIZATION:")
    paper_engine = PaperTradingEngine(
        initial_capital=1_000_000.0,
        data_dir=test_data_dir,
        transaction_cost_bps=10.0,
        slippage_bps=5.0,
        max_single_stock_weight=0.35,
        max_sector_weight=0.55,
        auto_load_state=False,
    )
    # Mock is_market_open to True for this historical controlled test
    paper_engine.data_adapter.is_market_open = lambda t=None: True
    print(f"  • Initial Paper Capital : ₹{paper_engine.broker.get_account().cash:,.2f}")
    print(f"  • State Directory       : {test_data_dir}")

    # 3. Rebalance Execution (Features -> ML -> Ranking -> Portfolio -> Risk -> Broker)
    print("\n[STEP 3] EXECUTE REBALANCE PIPELINE (Walk-Forward ML + Ranking + Portfolio + Risk):")
    rebal_res = paper_engine.execute_rebalance(
        candidate_panel=panel,
        market_bars_history=bar_dfs,
        current_quotes=current_quotes,
        current_volumes=current_volumes,
        as_of_time=t_decision,
        allocation_method="constrained",
    )
    print(f"  • Rebalance ID           : {rebal_res['rebalance_id']}")
    print(f"  • Total Orders Generated : {rebal_res['total_orders']}")
    print(f"  • Orders Filled          : {rebal_res['filled_orders']}")
    print(f"  • Orders Rejected        : {rebal_res['rejected_orders']}")

    # 4. Inspect Orders & Fills
    print("\n[STEP 4] EXECUTED PAPER ORDERS & FILLS:")
    orders = paper_engine.broker.orders
    for oid, o in orders.items():
        print(f"  • Order {oid} | {o.symbol:<10} | Side: {o.side.value:<4} | Req: {o.requested_quantity:4d} | Filled: {o.filled_quantity:4d} | AvgPrice: ₹{o.average_fill_price:8.2f} | Status: {o.status.value}")

    fills = paper_engine.broker.get_fills()
    print(f"\n  • Total Fills Executed: {len(fills)}")
    for f in fills:
        print(f"    - Fill {f.fill_id} | {f.symbol:<10} | Qty: {f.quantity:4d} @ ₹{f.price:8.2f} | Notional: ₹{f.total_notional:10,.2f} | Fee: ₹{f.transaction_cost:6.2f} | Slip: ₹{f.slippage:6.2f}")

    # 5. Inspect Account & Positions
    print("\n[STEP 5] POST-EXECUTION ACCOUNTING & POSITIONS:")
    acct = paper_engine.broker.get_account()
    print(f"  • Available Cash       : ₹{acct.cash:10,.2f}")
    print(f"  • Positions Value      : ₹{acct.positions_value:10,.2f}")
    print(f"  • Total Virtual Equity : ₹{acct.total_equity:10,.2f}")
    print(f"  • Realized Fees        : ₹{acct.total_fees:10,.2f}")
    print(f"  • Realized Slippage    : ₹{acct.total_slippage:10,.2f}")

    positions = paper_engine.broker.get_positions()
    for s, p in positions.items():
        w = p.market_value / acct.total_equity if acct.total_equity > 0 else 0.0
        print(f"  • Position: {s:<10} | Shares: {p.shares:4d} | AvgCost: ₹{p.average_cost:8.2f} | MktVal: ₹{p.market_value:10,.2f} | Weight: {w*100:5.2f}%")

    # 6. Mark to Market Next Day & Calculate P&L
    print("\n[STEP 6] NEXT-DAY MARKET PRICE UPDATE & P&L MARK-TO-MARKET:")
    # Simulate slight price movement on next day (+1% for Reliance, -0.5% for TCS, etc.)
    next_day_quotes = {
        "RELIANCE": current_quotes["RELIANCE"] * 1.010,
        "TCS": current_quotes["TCS"] * 0.995,
        "INFY": current_quotes["INFY"] * 1.008,
        "HDFCBANK": current_quotes["HDFCBANK"] * 1.002,
        "ICICIBANK": current_quotes["ICICIBANK"] * 0.998,
    }
    paper_engine.broker.update_market_panel(next_day_quotes)
    paper_engine.save_state()

    acct_next = paper_engine.broker.get_account()
    print(f"  • Updated Total Equity : ₹{acct_next.total_equity:10,.2f}")
    print(f"  • Unrealized P&L       : ₹{acct_next.unrealized_pnl:+10,.2f}")
    print(f"  • Daily P&L            : ₹{acct_next.daily_pnl:+10,.2f}")

    for s, p in paper_engine.broker.get_positions().items():
        print(f"  • Position: {s:<10} | Shares: {p.shares:4d} | NewPrice: ₹{p.current_price:8.2f} | Unrealized P&L: ₹{p.unrealized_pnl:+8.2f}")

    # 7. Persistence Verification
    print("\n[STEP 7] ATOMIC STATE PERSISTENCE VERIFICATION:")
    expected_files = ["account.json", "positions.json", "orders.json", "fills.json", "events.jsonl"]
    for fn in expected_files:
        fp = os.path.join(test_data_dir, fn)
        exists = os.path.exists(fp)
        size = os.path.getsize(fp) if exists else 0
        print(f"  • File: {fn:<15} | Status: {'EXISTS' if exists else 'MISSING'} | Size: {size:,} bytes")
        assert exists, f"Missing persistence file: {fn}"

    # 8. Process Restart Verification
    print("\n[STEP 8] PROCESS RESTART & STATE RESTORATION:")
    restarted_engine = PaperTradingEngine(
        initial_capital=1_000_000.0,
        data_dir=test_data_dir,
        auto_load_state=True,
    )
    acct_restarted = restarted_engine.broker.get_account()
    pos_restarted = restarted_engine.broker.get_positions()
    orders_restarted = restarted_engine.broker.orders
    fills_restarted = restarted_engine.broker.fills

    print(f"  • Restored Total Equity : ₹{acct_restarted.total_equity:10,.2f} (Match: {abs(acct_restarted.total_equity - acct_next.total_equity) < 1e-4})")
    print(f"  • Restored Cash         : ₹{acct_restarted.cash:10,.2f} (Match: {abs(acct_restarted.cash - acct_next.cash) < 1e-4})")
    print(f"  • Restored Positions    : {len(pos_restarted)} positions (Match: {len(pos_restarted) == len(positions)})")
    print(f"  • Restored Orders       : {len(orders_restarted)} orders (Match: {len(orders_restarted) == len(orders)})")
    print(f"  • Restored Fills        : {len(fills_restarted)} fills (Match: {len(fills_restarted) == len(fills)})")

    assert abs(acct_restarted.total_equity - acct_next.total_equity) < 1e-4
    assert len(pos_restarted) == len(positions)
    assert len(orders_restarted) == len(orders)
    assert len(fills_restarted) == len(fills)

    # 9. Order Deduplication on Restart
    print("\n[STEP 9] ORDER DEDUPLICATION ON RESTART:")
    # Attempting to resubmit the exact same order with the same idempotency key must be REJECTED
    first_order = list(orders_restarted.values())[0]
    dup_order = PaperOrder(
        symbol=first_order.symbol,
        side=first_order.side,
        order_type=first_order.order_type,
        requested_quantity=first_order.requested_quantity,
        idempotency_key=first_order.idempotency_key,
    )
    q_val = restarted_engine.data_adapter.validate_quote(dup_order.symbol, next_day_quotes[dup_order.symbol])
    res_dup = restarted_engine.order_manager.submit_order(dup_order, q_val, as_of_time=t_decision)
    print(f"  • Resubmitted Duplicate Order Status : {res_dup.status.value}")
    print(f"  • Rejection Reason                   : {res_dup.rejection_reason.value if res_dup.rejection_reason else 'None'}")
    assert res_dup.status == OrderStatus.REJECTED
    assert res_dup.rejection_reason == RejectionReason.DUPLICATE_ORDER
    print(f"  • Zero-Duplicate Invariant          : PASS (Idempotency key prevented double execution)")

    # 10. Reconciliation Audit
    print("\n[STEP 10] RECONCILIATION AUDIT:")
    recon = restarted_engine.reconcile_state()
    print(f"  • Reconciliation Status : {recon.status.value}")
    print(f"  • Is Clean              : {recon.is_clean}")
    print(f"  • Discrepancies Count   : {len(recon.discrepancies)}")
    assert recon.is_clean
    assert recon.status == ReconciliationStatus.MATCH

    print("\n" + "=" * 100)
    print("CONTROLLED END-TO-END PAPER EXECUTION & RESTART VERIFICATION COMPLETE.")
    print("=" * 100)

    # Cleanup test dir
    shutil.rmtree(test_data_dir, ignore_errors=True)


if __name__ == "__main__":
    run_e2e_verification()
