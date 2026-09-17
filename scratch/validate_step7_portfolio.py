"""
scratch/validate_step7_portfolio.py — Multi-Date Historical Portfolio Construction Validation.

SCOPE AND TERMINOLOGY DISCLAIMERS:
1. EMPIRICAL VALIDATION SCOPE:
   - Evaluated strictly on the 5-stock empirical dataset:
     RELIANCE, TCS, INFY, HDFCBANK, ICICIBANK.
   - Full 500-stock universe is NOT evaluated in this research prototype.
   - No claim is made regarding full 500-stock portfolio performance.

2. RESEARCH PROTOTYPE ONLY:
   - Expected return and risk metrics are model-based diagnostics.
   - They do NOT represent guaranteed trading profits.
   - No broker execution, paper trading, or live trading is implemented.

3. POINT-IN-TIME SAFETY:
   - Covariance, volatility, liquidity, and prices are strictly <= T.
   - Zero future look-ahead.
"""
from __future__ import annotations

import os
import sys
import copy
import pandas as pd
import numpy as np

ROOT_DIR = r"c:\Users\achie\OneDrive\Desktop\Trading-Bot"
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from data.market.storage import ParquetMarketDataStorage
from features.engine import FeatureEngine
from ml.equity.registry import ModelRegistry
from ml.equity.predict import EquityPredictor
from universe.universe_manager import UniverseManager
from ranking.config import RankingConfig
from ranking.ranker import CrossSectionalRanker
from portfolio.config import PortfolioConfig
from portfolio.portfolio_builder import PortfolioBuilder
from portfolio.models import PortfolioBuildResult, PortfolioPosition


def run_step7_validation():
    print("=" * 95)
    print("APEX QUANT — STEP 7: HISTORICAL MULTI-DATE PORTFOLIO CONSTRUCTION & RISK ALLOCATION")
    print("=" * 95)
    print("CRITICAL SCOPE DEFINITIONS:")
    print("  • Empirical Test Dataset   : 5 stocks (RELIANCE, TCS, INFY, HDFCBANK, ICICIBANK)")
    print("  • Full Universe Ingestion  : 500 stocks (DEFERRED to future steps)")
    print("  • Portfolio Mode           : Long-Only Cash Equity (No shorting, no leverage, no margin)")
    print("  • Execution Status         : Research diagnostic ONLY (Zero live/paper trading)")
    print("  • Point-in-Time Safety     : Strictly <= T data for prices, covariance, and liquidity")
    print("=" * 95)

    storage = ParquetMarketDataStorage()
    empirical_symbols = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]

    # 1. Feature Generation & Storage Ingestion
    print("\n[1/6] Ingesting Parquet market bars and generating features (2023-01-01 to 2024-04-30)...")
    engine = FeatureEngine()
    feature_set = engine.generate_panel_from_storage(
        storage=storage,
        symbols=empirical_symbols,
        start_date="2023-01-01",
        end_date="2024-04-30",
        is_adjusted=True,
    )
    panel = feature_set.data
    print(f"  • Ingested panel: {len(panel):,} rows across {feature_set.feature_count} features.")

    # 2. Step 5 ML Model Inference
    print("\n[2/6] Loading pre-trained Step 5 ML Model artifact...")
    registry = ModelRegistry()
    artifacts = registry.list_artifacts()
    target_version = artifacts[-1]["version"]
    print(f"  • Model artifact version: {target_version}")
    predictor = EquityPredictor.from_registry(target_version, registry=registry)
    preds = predictor.predict(panel)
    panel["predicted_return"] = preds["predicted_return"].values

    # Attach close prices
    price_dfs = []
    for sym in empirical_symbols:
        raw_df = storage.query_by_symbol(sym, is_adjusted=True)
        price_dfs.append(raw_df[["timestamp", "symbol", "close"]])
    prices_all = pd.concat(price_dfs, ignore_index=True)
    panel = panel.merge(prices_all, on=["timestamp", "symbol"], how="left")

    # 3. Market Bar Query for Risk & Pricing
    bar_dfs = {sym: storage.query_by_symbol(sym, is_adjusted=True) for sym in empirical_symbols}
    universe_mgr = UniverseManager()
    rank_config = RankingConfig(top_k=5, normalization_method="percentile")
    ranker = CrossSectionalRanker(config=rank_config, universe_manager=universe_mgr)

    # 4. Multi-Date Evaluation Setup
    eval_dates = [
        "2024-01-15", "2024-01-22", "2024-01-29",
        "2024-02-05", "2024-02-12", "2024-02-19", "2024-02-26",
        "2024-03-04", "2024-03-11", "2024-03-18",
    ]
    print(f"\n[3/6] Running Portfolio Construction across {len(eval_dates)} historical dates...")

    port_config = PortfolioConfig(
        max_positions=5,
        min_positions=1,
        max_single_stock_weight=0.35,
        max_sector_weight=0.55,
        max_gross_exposure=0.95,
        min_cash_weight=0.05,
        max_turnover=1.0,
        transaction_cost_bps=10.0,
        slippage_bps=5.0,
    )
    builder = PortfolioBuilder(config=port_config)

    methods = ["equal_weight", "score_weighted", "inverse_volatility", "constrained"]
    results_by_method = {m: [] for m in methods}
    initial_capital = 1_000_000.0  # ₹10 Lakh portfolio capital

    violations_count = 0
    integer_shares_valid = True
    no_negative_cash_valid = True

    for dt_str in eval_dates:
        dt_val = pd.to_datetime(dt_str, utc=True)
        slice_df = panel[panel["timestamp"].dt.date == dt_val.date()].copy()
        if slice_df.empty:
            continue

        # Step 6 Point-in-Time Ranking
        ranked_uni = ranker.rank_cross_section(slice_df, as_of_date=dt_str)

        for m in methods:
            res = builder.build_portfolio(
                ranked_universe=ranked_uni,
                market_bars=bar_dfs,
                total_capital=initial_capital,
                method=m,
            )
            results_by_method[m].append((dt_str, res))

            # Constraint audits
            # 1. Gross exposure <= 0.95 + 1e-4
            if res.gross_exposure > port_config.max_gross_exposure + 1e-4:
                violations_count += 1
            # 2. Cash >= 0.0
            if res.cash < -1e-4:
                no_negative_cash_valid = False
                violations_count += 1
            # 3. Integer shares
            for sym, pos in res.positions.items():
                if not isinstance(pos.target_shares, int) or pos.target_shares < 0:
                    integer_shares_valid = False
                    violations_count += 1
                if pos.target_weight > port_config.max_single_stock_weight + 1e-3:
                    violations_count += 1
            # 4. Sector constraint
            for sec, sec_w in res.diagnostics.sector_weights.items():
                if sec_w > port_config.max_sector_weight + 1e-3:
                    violations_count += 1

    # 5. Summary Table for Evaluation Dates
    print("\n[4/6] Historical Portfolio Allocations across dates:")
    print("-" * 125)
    print(f"{'Date':<11} | {'Method':<18} | {'Selected':<8} | {'Gross Exp':<9} | {'Cash (₹)':<10} | {'Exp Ret':<8} | {'Exp Vol':<8} | {'Est Cost':<9} | {'HHI':<6} | {'Top Sector'}")
    print("-" * 125)

    sample_dates = ["2024-01-15", "2024-02-19", "2024-03-18"]
    for dt_str in sample_dates:
        for m in methods:
            matches = [r for d, r in results_by_method[m] if d == dt_str]
            if not matches:
                continue
            res = matches[0]
            top_sec = f"{res.diagnostics.largest_sector} ({res.diagnostics.sector_weights.get(res.diagnostics.largest_sector, 0.0)*100:.1f}%)" if res.diagnostics.largest_sector else "None"
            print(
                f"{dt_str:<11} | "
                f"{res.allocation_method:<18} | "
                f"{res.selected_count:<8} | "
                f"{res.gross_exposure*100:6.1f}%   | "
                f"₹{res.cash:9,.0f} | "
                f"{res.risk_metrics.expected_return*100:+6.2f}% | "
                f"{res.risk_metrics.portfolio_volatility*100:6.2f}% | "
                f"₹{res.diagnostics.estimated_transaction_cost:7,.0f} | "
                f"{res.diagnostics.hhi_concentration:.3f} | "
                f"{top_sec}"
            )
        print("-" * 125)

    # 6. Aggregate Comparison of Allocation Methods
    print("\n[5/6] Aggregate Comparison of Allocation Methods across 10 Historical Dates:")
    print("-" * 115)
    print(f"{'Allocation Method':<22} | {'Avg Count':<9} | {'Avg Gross':<10} | {'Avg Exp Ret':<12} | {'Avg Exp Vol':<12} | {'Avg Ret/Risk':<12} | {'Avg HHI':<8}")
    print("-" * 115)

    for m in methods:
        runs = [r for _, r in results_by_method[m]]
        avg_cnt = np.mean([r.selected_count for r in runs])
        avg_gross = np.mean([r.gross_exposure for r in runs]) * 100
        avg_ret = np.mean([r.risk_metrics.expected_return for r in runs]) * 100
        avg_vol = np.mean([r.risk_metrics.portfolio_volatility for r in runs]) * 100
        avg_ratio = np.mean([r.risk_metrics.return_to_risk_ratio for r in runs])
        avg_hhi = np.mean([r.diagnostics.hhi_concentration for r in runs])
        print(
            f"{m:<22} | "
            f"{avg_cnt:<9.1f} | "
            f"{avg_gross:6.1f}%    | "
            f"{avg_ret:+7.2f}%     | "
            f"{avg_vol:6.2f}%     | "
            f"{avg_ratio:+8.2f}     | "
            f"{avg_hhi:.4f}"
        )
    print("-" * 115)

    # 7. Verification Audits: Leakage, Determinism, and Infeasibility
    print("\n[6/6] Executing Safety Audits...")

    # Audit 1: Determinism
    dt_det = "2024-01-15"
    slice_det = panel[panel["timestamp"].dt.date == pd.to_datetime(dt_det, utc=True).date()].copy()
    ranked_det = ranker.rank_cross_section(slice_det, as_of_date=dt_det)
    res_det1 = builder.build_portfolio(ranked_det, bar_dfs, total_capital=1_000_000.0, method="constrained")
    res_det2 = builder.build_portfolio(ranked_det, bar_dfs, total_capital=1_000_000.0, method="constrained")
    det_pass = (res_det1.positions.keys() == res_det2.positions.keys()) and all(
        res_det1.positions[s].target_shares == res_det2.positions[s].target_shares for s in res_det1.positions
    )
    print(f"  • Determinism Test        : {'PASS' if det_pass else 'FAIL'}")

    # Audit 2: Point-In-Time Leakage Audit
    # Corrupt future market bar prices and predictions at T + 10 days
    dt_t = "2024-01-15"
    bars_corrupted = {s: df.copy() for s, df in bar_dfs.items()}
    for s, df in bars_corrupted.items():
        mask_future = pd.to_datetime(df["timestamp"]) > pd.to_datetime(dt_t, utc=True)
        bars_corrupted[s].loc[mask_future, "close"] = df.loc[mask_future, "close"] * 100.0
        bars_corrupted[s].loc[mask_future, "volume"] = df.loc[mask_future, "volume"] * 1000.0

    res_corrupted = builder.build_portfolio(ranked_det, bars_corrupted, total_capital=1_000_000.0, method="constrained")
    leak_pass = (res_det1.positions.keys() == res_corrupted.positions.keys()) and all(
        res_det1.positions[s].target_shares == res_corrupted.positions[s].target_shares for s in res_det1.positions
    ) and abs(res_det1.cash - res_corrupted.cash) < 1e-4
    print(f"  • Zero-Lookahead Leakage  : {'PASS' if leak_pass else 'FAIL'}")

    # Audit 3: Infeasibility Handling
    # Low capital test
    res_tiny = builder.build_portfolio(ranked_det, bar_dfs, total_capital=500.0, method="constrained")
    infeas_pass = (res_tiny.selected_count == 0) and (res_tiny.cash == 500.0)
    print(f"  • Infeasibility Handling  : {'PASS' if infeas_pass else 'FAIL'}")

    # Audit 4: Constraints & Integer Shares
    print(f"  • Constraint Violations   : {violations_count} (Expected: 0)")
    print(f"  • Integer Shares Audit    : {'PASS' if integer_shares_valid else 'FAIL'}")
    print(f"  • Non-Negative Cash Audit : {'PASS' if no_negative_cash_valid else 'FAIL'}")

    print("\n" + "=" * 95)
    print("STEP 7 PORTFOLIO CONSTRUCTION HISTORICAL VALIDATION COMPLETE.")
    print("=" * 95)


if __name__ == "__main__":
    run_step7_validation()
