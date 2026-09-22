"""
scratch/run_phases_8_to_11.py — Targeted runner for Step 13.8 Phases 8-11.

This script runs ONLY the 4 missing phases to complete the research:
- Phase 8: Cost Sensitivity Sweep  -> cost_sensitivity_sweep.csv
- Phase 9: Factor Exposure         -> factor_exposure_analysis.json
- Phase 10: Anti-Overfitting Audit -> anti_overfitting_audit.json
- Phase 11: Reproducibility Manifest -> reproducibility_manifest.json

Phases 1-7 artifacts already exist and are preserved.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

import numpy as np
import pandas as pd
from scipy import stats

ROOT_DIR = Path(r"c:\Users\achie\OneDrive\Desktop\Trading-Bot")
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Import from the main research script
from scratch.run_alpha_v3_research import (
    TurnoverPenalizedOptimizer,
    run_single_simulation,
    run_phase_10_anti_overfitting,
    run_phase_11_reproducibility,
    RESULTS_DIR,
)
from data.market.storage import ParquetMarketDataStorage
from features.engine import FeatureEngine
from universe.constituents import CuratedNifty500Provider

def main() -> None:
    print("\n" + "=" * 78)
    print("  APEX-QUANT STEP 13.8: PHASES 8-11 TARGETED RUNNER")
    print("=" * 78)

    storage = ParquetMarketDataStorage()

    # Load manifest to get available/unavailable symbols
    manifest_path = RESULTS_DIR / "data_availability_manifest.json"
    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    available_symbols = manifest["available_symbols"]
    unavailable_symbols = manifest["unavailable_symbols"]
    print(f"[OK] Loaded manifest: {len(available_symbols)} available, {len(unavailable_symbols)} unavailable")

    # Load panel for all 48 available symbols
    print("\n---> Loading full historical panel for all 48 available symbols...")
    fe = FeatureEngine()
    fs_full = fe.generate_panel_from_storage(
        storage=storage,
        symbols=available_symbols,
        start_date="2022-01-01",
        end_date="2026-09-16",
        is_adjusted=True,
    )

    # Fetch price bars
    price_dfs = []
    bar_dfs_all: dict = {}
    for s in available_symbols:
        df_b = storage.query_by_symbol(s, is_adjusted=True)
        assert df_b is not None and not df_b.empty
        bar_dfs_all[s] = df_b
        price_dfs.append(df_b[["timestamp", "symbol", "close"]])
    prices_all = pd.concat(price_dfs, ignore_index=True)

    panel_full = fs_full.data.merge(prices_all, on=["timestamp", "symbol"], how="left")
    catalog_stocks = CuratedNifty500Provider().get_stocks()
    sec_map = {s.symbol: s.sector for s in catalog_stocks}
    panel_full["sector"] = panel_full["symbol"].map(sec_map).fillna("Unclassified")
    print(f"[OK] Panel loaded: {len(panel_full)} rows, {panel_full['symbol'].nunique()} symbols")

    # =======================================================================
    # PHASE 8: COST SENSITIVITY SWEEP
    # =======================================================================
    print("\n" + "=" * 78)
    print("  PHASE 8: COST SENSITIVITY & FRICTION ROBUSTNESS SWEEP")
    print("=" * 78)

    friction_levels = [0.0, 10.0, 20.0, 30.0, 50.0]
    sweep_rows = []

    strategies_to_test = [
        ("Variant A (Constrained Weekly Unpenalized)", "weekly", "constrained", None, 0.0),
        ("Variant B (Turnover-Penalized Weekly)", "weekly", "constrained", TurnoverPenalizedOptimizer(gamma_turnover=1.0), 0.0),
        ("Variant E (Turnover-Penalized Monthly + Deadband)", "monthly", "constrained", TurnoverPenalizedOptimizer(gamma_turnover=1.0), 0.025),
        ("Benchmark: Equal Weight Monthly", "monthly", "equal_weight", None, 0.0),
    ]

    for strat_name, rebal_freq, alloc_meth, opt, dband in strategies_to_test:
        use_ml_flag = alloc_meth == "constrained"
        max_p = 15 if alloc_meth == "constrained" else len(available_symbols)
        max_weight = 0.15 if max_p == 15 else 0.10

        print(f"\n  Running strategy: {strat_name}")
        row = {"strategy": strat_name}
        for bps in friction_levels:
            half_fee = bps * 0.67
            half_slip = bps * 0.33
            print(f"    bps={int(bps)}...", end="", flush=True)
            res = run_single_simulation(
                candidate_panel=panel_full,
                market_bars=bar_dfs_all,
                symbols=available_symbols,
                start_date="2023-01-01",
                end_date="2026-09-16",
                rebalance_frequency=rebal_freq,
                allocation_method=alloc_meth,
                optimizer=opt,
                deadband=dband,
                max_positions=max_p,
                max_single_stock_weight=max_weight,
                transaction_cost_bps=half_fee,
                slippage_bps=half_slip,
                use_ml=use_ml_flag,
            )
            m = res["metrics"]
            tot_costs = m.total_fees + m.total_slippage
            row[f"{int(bps)}_bps_return_pct"] = round(m.total_return * 100.0, 2)
            row[f"{int(bps)}_bps_sharpe"] = round(m.sharpe_ratio, 3)
            row[f"{int(bps)}_bps_costs_inr"] = round(tot_costs, 2)
            print(f" ret={m.total_return * 100:.2f}%", flush=True)

        ret_0 = row["0_bps_return_pct"]
        ret_50 = row["50_bps_return_pct"]
        row["return_drag_0_to_50_pct"] = round(ret_0 - ret_50, 2)
        row["survives_50_bps"] = ret_50 > 0.0
        sweep_rows.append(row)

    sweep_df = pd.DataFrame(sweep_rows)
    csv_out = RESULTS_DIR / "cost_sensitivity_sweep.csv"
    sweep_df.to_csv(csv_out, index=False)
    print(f"\n[OK] Cost sensitivity sweep saved to: {csv_out}")
    for _, r in sweep_df.iterrows():
        print(f"  {r['strategy']:<48} | 0 bps: {r['0_bps_return_pct']:+6.2f}% | 50 bps: {r['50_bps_return_pct']:+6.2f}% | Drag: {r['return_drag_0_to_50_pct']:5.2f}%")

    # Validate monotonicity
    for _, row in sweep_df.iterrows():
        r0 = row["0_bps_return_pct"]
        r10 = row["10_bps_return_pct"]
        r20 = row["20_bps_return_pct"]
        r30 = row["30_bps_return_pct"]
        r50 = row["50_bps_return_pct"]
        ok = r0 >= r10 >= r20 >= r30 >= r50
        print(f"  Monotonicity [{row['strategy'][:30]}]: {'PASS' if ok else 'FAIL'} [{r0:.2f}, {r10:.2f}, {r20:.2f}, {r30:.2f}, {r50:.2f}]")

    # =======================================================================
    # PHASE 9: FACTOR EXPOSURE
    # =======================================================================
    print("\n" + "=" * 78)
    print("  PHASE 9: FACTOR EXPOSURE & PASSIVE RETURN ATTRIBUTION")
    print("=" * 78)

    # We need daily returns from Variant B, Variant E, 5-stock benchmark
    # Re-run these specific simulations to get daily return series
    print("  Re-running simulations for factor exposure daily returns...")

    syms_5 = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]
    bar_dfs_5 = {s: bar_dfs_all[s] for s in syms_5 if s in bar_dfs_all}
    panel_5stock = panel_full[panel_full["symbol"].isin(syms_5)].copy()

    daily_returns_cache = {}

    # Market benchmark (EW Broader Monthly)
    print("  EW Broader Monthly (market benchmark)...", flush=True)
    res_ew_m = run_single_simulation(
        candidate_panel=panel_full,
        market_bars=bar_dfs_all,
        symbols=available_symbols,
        start_date="2023-01-01",
        end_date="2026-09-16",
        rebalance_frequency="monthly",
        allocation_method="equal_weight",
        max_positions=len(available_symbols),
        max_single_stock_weight=0.10,
        use_ml=False,
    )
    daily_returns_cache["Full Multi-Year_EW_Broader_Monthly"] = res_ew_m["daily_returns"]
    print(f"    EW Monthly ret: {res_ew_m['metrics'].total_return * 100:.2f}%")

    # Variant B
    print("  Variant B (Turnover-Penalized Weekly)...", flush=True)
    res_var_b = run_single_simulation(
        candidate_panel=panel_full,
        market_bars=bar_dfs_all,
        symbols=available_symbols,
        start_date="2023-01-01",
        end_date="2026-09-16",
        rebalance_frequency="weekly",
        allocation_method="constrained",
        optimizer=TurnoverPenalizedOptimizer(gamma_turnover=1.0),
        max_positions=15,
        max_single_stock_weight=0.15,
        max_sector_weight=0.35,
        use_ml=True,
    )
    daily_returns_cache["Full Multi-Year_Var_B_Penalized_Weekly"] = res_var_b["daily_returns"]
    print(f"    Var B ret: {res_var_b['metrics'].total_return * 100:.2f}%")

    # Variant E
    print("  Variant E (Turnover-Penalized Monthly + Deadband)...", flush=True)
    res_var_e = run_single_simulation(
        candidate_panel=panel_full,
        market_bars=bar_dfs_all,
        symbols=available_symbols,
        start_date="2023-01-01",
        end_date="2026-09-16",
        rebalance_frequency="monthly",
        allocation_method="constrained",
        optimizer=TurnoverPenalizedOptimizer(gamma_turnover=1.0),
        deadband=0.025,
        max_positions=15,
        max_single_stock_weight=0.15,
        max_sector_weight=0.35,
        use_ml=True,
    )
    daily_returns_cache["Full Multi-Year_Var_E_Penalized_Monthly_Deadband"] = res_var_e["daily_returns"]
    print(f"    Var E ret: {res_var_e['metrics'].total_return * 100:.2f}%")

    # 5-stock EW baseline
    print("  EW 5-Stock Weekly...", flush=True)
    res_ew_5 = run_single_simulation(
        candidate_panel=panel_5stock,
        market_bars=bar_dfs_5,
        symbols=syms_5,
        start_date="2023-01-01",
        end_date="2026-09-16",
        rebalance_frequency="weekly",
        allocation_method="equal_weight",
        max_positions=5,
        max_single_stock_weight=0.35,
        use_ml=False,
    )
    daily_returns_cache["Full Multi-Year_EW_5Stock_Weekly"] = res_ew_5["daily_returns"]
    print(f"    EW 5-stock ret: {res_ew_5['metrics'].total_return * 100:.2f}%")

    # Now compute factor attribution
    mkt_key = "Full Multi-Year_EW_Broader_Monthly"
    r_mkt = daily_returns_cache[mkt_key]

    active_keys = [
        ("Variant B (Turnover-Penalized Weekly)", "Full Multi-Year_Var_B_Penalized_Weekly"),
        ("Variant E (Turnover-Penalized Monthly + Deadband)", "Full Multi-Year_Var_E_Penalized_Monthly_Deadband"),
        ("5-Stock Equal Weight Baseline", "Full Multi-Year_EW_5Stock_Weekly"),
    ]

    factor_results = []
    for label, a_key in active_keys:
        if a_key not in daily_returns_cache:
            continue
        r_strat = daily_returns_cache[a_key]
        aligned = pd.DataFrame({"strat": r_strat, "mkt": r_mkt}).dropna()
        if len(aligned) < 50:
            print(f"  [WARN] Insufficient aligned data for {label}: {len(aligned)} rows")
            continue

        y = aligned["strat"].values
        x = aligned["mkt"].values

        slope, intercept, r_val, p_val, std_err = stats.linregress(x, y)
        ann_alpha = float(intercept * 252.0 * 100.0)
        r_sq = float(r_val ** 2)

        factor_results.append({
            "strategy": label,
            "benchmark": "Equal Weight Broader Universe Monthly",
            "period": "Full Multi-Year (2023-01-01 to 2026-09-16)",
            "market_beta": round(float(slope), 4),
            "annualized_alpha_pct": round(ann_alpha, 2),
            "r_squared": round(r_sq, 4),
            "correlation": round(float(r_val), 4),
            "p_value": round(float(p_val), 6),
            "interpretation": "True alpha present" if ann_alpha > 0 and p_val < 0.05 else "Returns predominantly driven by passive market exposure / negative alpha after costs",
        })

    json_out = RESULTS_DIR / "factor_exposure_analysis.json"
    with open(json_out, "w") as f:
        json.dump({"factor_attributions": factor_results}, f, indent=2)

    print(f"\n[OK] Factor exposure analysis saved to: {json_out}")
    for fa in factor_results:
        print(f"  {fa['strategy']:<48} | Beta: {fa['market_beta']:5.3f} | Alpha: {fa['annualized_alpha_pct']:+5.2f}% p.a. | R^2: {fa['r_squared']:5.3f}")

    # =======================================================================
    # PHASE 10: ANTI-OVERFITTING AUDIT
    # =======================================================================
    mutation_res = run_phase_10_anti_overfitting(storage, available_symbols)

    # =======================================================================
    # PHASE 11: REPRODUCIBILITY MANIFEST
    # =======================================================================
    repro_manifest = run_phase_11_reproducibility(available_symbols, unavailable_symbols)

    print("\n" + "=" * 78)
    print("  [SUCCESS] PHASES 8-11 COMPLETED. ALL 4 MISSING ARTIFACTS GENERATED.")
    print(f"  Artifacts saved to: {RESULTS_DIR}")
    print("=" * 78 + "\n")

    # Print all artifact status
    required = [
        "data_availability_manifest.json", "data_quality_report.csv", "pit_safety_audit.json",
        "feature_ic_analysis.json", "feature_correlation_matrix.csv", "model_comparison.json",
        "alpha_v3_scorecard.csv", "walk_forward_evaluation.json", "cost_sensitivity_sweep.csv",
        "factor_exposure_analysis.json", "anti_overfitting_audit.json", "reproducibility_manifest.json",
    ]
    print("  Final artifact status:")
    all_present = True
    for name in required:
        p = RESULTS_DIR / name
        if p.exists() and p.stat().st_size > 50:
            print(f"  [OK] {name} ({p.stat().st_size:,} bytes)")
        else:
            print(f"  [MISSING/EMPTY] {name}")
            all_present = False
    print(f"\n  All 12 artifacts present: {all_present}")


if __name__ == "__main__":
    main()
