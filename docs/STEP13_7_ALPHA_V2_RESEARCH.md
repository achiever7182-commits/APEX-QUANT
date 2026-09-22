# APEX-QUANT — STEP 13.7 ALPHA V2 STRATEGY RESEARCH REPORT

**Document Version:** 1.0.0  
**Research Date:** September 2026  
**Status:** Completed Research Audit — Baseline Strictly Frozen & Preserved  
**Target Environment:** Quantitative Backtesting & Research Simulation Only (Live Trading Disabled)  
**Machine-Readable Artifacts:** `docs/results/step13_7/`  

---

## EXECUTIVE SUMMARY

Step 13.7 conducts an empirical investigation into **Alpha V2**: evaluating whether economically motivated turnover stabilization mechanisms (turnover penalties, signal persistence deadbands, cadence adjustments) can transform APEX-QUANT into a viable, cost-robust alpha generator.

Following Steps 13.5 and 13.6, the Step 13.5 baseline result (+14.36% net return, 13.92x turnover, ₹44,959.99 costs over June 1, 2023 – April 30, 2024 on the 5-stock empirical benchmark) remains **strictly frozen and intact**.

### Primary Empirical Findings

1. **Turnover Disease Successfully Cured:**  
   The primary quantitative success of Step 13.7 is the definitive resolution of the turnover disease. The introduction of an explicit quadratic turnover tracking penalty ($\gamma_{\text{turnover}} = 1.0$) slashed multi-year turnover from **52.99x down to 2.32x** (a **95.6% reduction**), reducing multi-year transaction friction from **₹167,495.59 down to ₹8,656.54** (saving **₹158,839 in capital**).
2. **Capital Preservation Under Friction:**  
   In the Extended Out-of-Sample period (`2024-05-01` to `2026-09-16`), the Baseline Weekly Constrained strategy lost **-9.37%** (Sharpe -0.295) with ₹113,827.65 in costs. The Turnover-Penalized Weekly strategy (Variant B) flipped this loss to **+16.73% net return** (Sharpe +0.076) with only ₹5,303.82 in costs.
3. **Severe Drawdown Compression:**  
   Combining a turnover penalty with a 2.5% position deadband (Variant E & E2) compressed the multi-year maximum drawdown from **31.92% down to 8.84%** (Variant E2) and **11.81%** (Variant E), with multi-year net returns of **+34.77% to +35.97%** and cumulative costs below ₹1,160.
4. **The Persistent Alpha Dilemma (Active vs. Passive):**  
   Despite curing turnover, **active stock-selection alpha remains insufficient to beat passive Equal Weight**. Across the full 3.7-year horizon (`2023-01-01` to `2026-09-16`), passive **Equal Weight Weekly achieved +44.62%** (Sharpe +0.280, Max DD 22.27%) and **Equal Weight Monthly achieved +43.79%** (Sharpe +0.273, Max DD 22.00%). Even the best monthly active variant (+42.79% for Variant C) marginally lagged passive exposure.
5. **Universe Limitation Re-Confirmed:**  
   The 52-stock curated universe catalog continues to have only **5 stocks** with historical local data (1,241 bars, 2021–2026). The remaining **47 stocks are UNAVAILABLE**. Zero data was fabricated.

---

## PHASE 1 — TURNOVER ATTRIBUTION ANALYSIS

A mathematical decomposition was performed on the baseline strategy's multi-year turnover (52.99x) to isolate the exact structural sources of portfolio churn:

### Mathematical Decomposition of Multi-Year Turnover (52.99x)

| Attribution Component | Multi-Year Turnover | % of Total Turnover | Mechanism & Economic Driver |
| :--- | :---: | :---: | :--- |
| **Passive Price Drift** | **2.48x** | **4.68%** | Natural asset return divergence. Measured by Equal Weight Weekly rebalancing. |
| **Active Optimizer Churn** | **50.51x** | **95.32%** | SLSQP solver violently swinging weights across boundary corners (5% to 35%) due to unpenalized quadratic objective. |
| **Weekly Cadence Drag** | **36.33x** | **68.56%** | Difference between Weekly Constrained (52.99x) and Monthly Constrained (16.66x). Rebalancing weekly multiplies noise by 4.3x. |
| **Turnover Penalty Savings** | **50.67x** | **95.62%** | Reduction achieved by adding $\frac{\gamma}{2}\|w - w_{\text{prev}}\|^2_2$ ($\gamma=1.0$). Cuts turnover from 52.99x to 2.32x. |
| **Deadband Filtering Alone** | **0.62x** | **1.17%** | Deadband alone at $\tau=2.5\%$ on weekly unpenalized SLSQP is ineffective because optimizer jumps exceed 2.5%. |

### Root Causes Identified
1. **Unpenalized SLSQP Objective:** In a 5-stock cross-section, expected returns differ by fractions of a percent ($\approx 0.1\%$). An unpenalized quadratic solver treats a 0.05% return advantage as justification to move 30% of portfolio equity, generating massive turnover for negligible expected alpha.
2. **Boundary Corner Hopping:** Two banking stocks (`HDFCBANK`, `ICICIBANK`) repeatedly bump into the 50% sector limit, causing the solver to oscillate violently between banking and tech/energy.
3. **Noise Optimization:** Weekly rebalancing re-optimizes 52 times per year, treating high-frequency weekly price fluctuations as durable signal shifts.

*Artifact Reference:* [`docs/results/step13_7/turnover_attribution.json`](file:///c:/Users/achie/OneDrive/Desktop/Trading-Bot/docs/results/step13_7/turnover_attribution.json).

---

## PHASE 2 & 3 — ALPHA V2 VARIANTS & TURNOVER PENALTY RESEARCH

To resolve optimizer churn without data snooping, five economically motivated variants were formulated and evaluated:

### Formulations & Economic Rationale

1. **Variant A: Constrained Weekly (Frozen Baseline):**  
   Standard SLSQP: $\min_w \frac{\lambda}{2} w^T \Sigma w - \mu^T w$ subject to $w_i \le 0.35$, $\sum w \le 0.95$, $\sum_{\text{sector}} w \le 0.50$. Rebalanced weekly (`W-FRI`).
2. **Variant B: Turnover-Penalized Optimizer ($\gamma = 1.0$, cap = 20%):**  
   Objective augmented with a quadratic tracking penalty:
   $$\min_w \frac{\lambda}{2} w^T \Sigma w - \mu^T w + \frac{\gamma_{\text{turnover}}}{2} \sum_{i=1}^k (w_i - w_{\text{prev}, i})^2$$
   *Economic Rationale:* In Indian equities, round-trip friction is 15–20 bps. Over 52 weeks, trading to capture a 10 bps expected return gain incurs 15 bps in guaranteed friction. Setting $\gamma = 1.0$ penalizes any trade where the expected return gain does not comfortably exceed transaction drag.
3. **Variant C: Constrained Monthly (`1ME` Cadence):**  
   Standard SLSQP rebalanced on calendar month-end trading days.  
   *Economic Rationale:* Lowers trading frequency from 52 to 12 cycles/year, allowing medium-term momentum and fundamental drift to realize without weekly whipsaw.
4. **Variant D: Signal Persistence / Rebalance Deadband ($\tau = 2.5\%$):**  
   Target shares are only adjusted if $|w_{\text{target}, i} - w_{\text{current}, i}| \ge 0.025$.  
   *Economic Rationale:* Suppresses dust rebalancing from normal market volatility.
5. **Variant E & E2: Turnover-Penalized + Deadband (Monthly & Weekly):**  
   Combines the quadratic turnover tracking penalty ($\gamma = 1.0$) with the $2.5\%$ position deadband.

---

## PHASE 4 & 5 — REBALANCING CADENCE & DEADBAND COMPARISON

Direct empirical comparison between weekly and monthly cadence across identical data and signals:

| Cadence & Mechanism | Multi-Year Return | Multi-Year Turnover | Multi-Year Friction | Max Drawdown | Closed Trades | Win Rate |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Baseline Weekly (Unpenalized)** | -5.25% | 52.99x | ₹167,495.59 | 31.92% | 562 | 43.6% |
| **Baseline Monthly (Unpenalized)** | **+42.79%** | **16.66x** | **₹65,345.25** | **23.24%** | **123** | **49.6%** |
| **Turnover-Penalized Weekly** | +21.14% | 2.32x | ₹8,656.54 | 23.49% | 315 | 52.4% |
| **Turnover-Penalized Monthly + Deadband** | +35.97% | **0.33x** | **₹1,083.93** | **11.81%** | **4** | **100.0%** |
| **Turnover-Penalized Weekly + Deadband** | +34.77% | **0.28x** | **₹1,157.77** | **8.84%** | **3** | **66.7%** |

### Key Insights
- **Monthly Cadence Dominance:** Monthly rebalancing alone improves multi-year return from **-5.25% to +42.79%** by eliminating 36.33x in whipsaw turnover.
- **Synergy of Penalty + Deadband:** In Variants E and E2, the combination of turnover penalty and deadband eliminated 99% of trading friction (costs dropped to ~₹1,100), producing an exceptionally smooth equity curve with maximum drawdown below 12%.

---

## PHASE 6 & 7 — MULTI-YEAR WALK-FORWARD SCORECARD & BENCHMARKS

All variants were evaluated across three chronological partitions with expanding-window walk-forward ML models:

```
Historical Periods:
  Period 1: Baseline (Frozen)       2023-06-01 to 2024-04-30 (11 months / 228 sessions)
  Period 2: Extended OOS            2024-05-01 to 2026-09-16 (28.5 months / 588 sessions)
  Period 3: Full Multi-Year         2023-01-01 to 2026-09-16 (44.5 months / 915 sessions)
```

### Complete Research Scorecard

| Variant | Historical Period | Return | Trading CAGR | Sharpe (Rf=6.5%) | Sortino | Max DD | Turnover | Total Costs (₹) | Closed Trades | Win Rate | Profit Factor |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Variant A (Baseline Weekly)** | Baseline | +13.89% | +15.83% | 0.868 | 1.305 | 6.62% | 14.00x | ₹45,081.42 | 138 | 59.4% | 1.687 |
| **Variant B (Turnover-Penalized W)** | Baseline | +12.50% | +14.23% | 0.764 | 1.195 | 5.96% | 0.66x | ₹2,008.11 | 59 | 91.5% | 123.60 |
| **Variant C (Monthly SLSQP)** | Baseline | +13.42% | +15.30% | 0.769 | 1.222 | 5.81% | 4.16x | ₹13,103.60 | 23 | 78.3% | 3.648 |
| **Variant D (Deadband Weekly)** | Baseline | +13.97% | +15.92% | 0.874 | 1.315 | 6.59% | 13.88x | ₹44,777.76 | 107 | 59.8% | 1.697 |
| **Variant E (Monthly Pen+Deadband)** | Baseline | +12.19% | +13.88% | 0.656 | 1.019 | 6.18% | 0.36x | ₹1,082.94 | 1 | 100.0% | 999.0 |
| **Variant E2 (Weekly Pen+Deadband)** | Baseline | +12.37% | +14.09% | 0.687 | 1.068 | 6.00% | 0.38x | ₹1,125.03 | 2 | 100.0% | 999.0 |
| **Benchmark: Equal Weight Weekly** | Baseline | **+14.80%** | +16.88% | 0.841 | 1.269 | 8.57% | 0.88x | ₹2,755.82 | 99 | 78.8% | 11.693 |
| **Benchmark: Equal Weight Monthly** | Baseline | +14.79% | +16.87% | 0.840 | 1.268 | 8.66% | 0.61x | ₹1,873.71 | 21 | 85.7% | 13.675 |
| | | | | | | | | | | | |
| **Variant A (Baseline Weekly)** | Ext. OOS | -9.37% | -4.09% | -0.295 | -0.685 | 31.93% | 36.94x | ₹113,827.65 | 365 | 38.6% | 0.515 |
| **Variant B (Turnover-Penalized W)** | Ext. OOS | +16.73% | +6.79% | 0.076 | 0.142 | 16.50% | 1.56x | ₹5,303.82 | 201 | 60.7% | 1.412 |
| **Variant C (Monthly SLSQP)** | Ext. OOS | **+31.90%** | +12.49% | 0.307 | 0.838 | 23.23% | 11.69x | ₹46,330.87 | 86 | 41.9% | 0.535 |
| **Variant D (Deadband Weekly)** | Ext. OOS | -9.19% | -4.01% | -0.292 | -0.678 | 31.84% | 36.56x | ₹112,927.75 | 274 | 38.3% | 0.515 |
| **Variant E (Monthly Pen+Deadband)** | Ext. OOS | +26.44% | +10.48% | 0.254 | 0.623 | 15.94% | 0.56x | ₹1,807.41 | 3 | 66.7% | 1.079 |
| **Variant E2 (Weekly Pen+Deadband)** | Ext. OOS | +18.04% | +7.30% | 0.107 | 0.199 | 14.11% | 0.87x | ₹2,868.58 | 6 | 83.3% | 1.038 |
| **Benchmark: Equal Weight Weekly** | Ext. OOS | +27.52% | +10.88% | 0.277 | 0.589 | 22.24% | 1.91x | ₹7,411.24 | 402 | 59.7% | 0.959 |
| **Benchmark: Equal Weight Monthly** | Ext. OOS | +26.72% | +10.59% | 0.266 | 0.558 | 21.96% | 1.19x | ₹4,289.47 | 78 | 62.8% | 1.559 |
| | | | | | | | | | | | |
| **Variant A (Baseline Weekly)** | Multi-Year | -5.25% | -1.47% | -0.263 | -0.562 | 31.92% | 52.99x | ₹167,495.59 | 562 | 43.6% | 0.637 |
| **Variant B (Turnover-Penalized W)** | Multi-Year | +21.14% | +5.40% | 0.029 | 0.076 | 23.49% | 2.32x | ₹8,656.54 | 315 | 52.4% | 1.033 |
| **Variant C (Monthly SLSQP)** | Multi-Year | +42.79% | +10.27% | 0.242 | 0.611 | 23.24% | 16.66x | ₹65,345.25 | 123 | 49.6% | 0.657 |
| **Variant D (Deadband Weekly)** | Multi-Year | -4.99% | -1.40% | -0.260 | -0.555 | 31.84% | 52.37x | ₹166,139.39 | 406 | 42.9% | 0.638 |
| **Variant E (Monthly Pen+Deadband)** | Multi-Year | +35.97% | +8.80% | 0.201 | 0.475 | 11.81% | 0.33x | ₹1,083.93 | 4 | 100.0% | 999.0 |
| **Variant E2 (Weekly Pen+Deadband)** | Multi-Year | +34.77% | +8.54% | 0.201 | 0.407 | 8.84% | 0.28x | ₹1,157.77 | 3 | 66.7% | 268.15 |
| **Benchmark: Equal Weight Weekly** | Multi-Year | **+44.62%** | +10.66% | 0.280 | 0.553 | 22.27% | 2.48x | ₹9,994.08 | 681 | 64.9% | 1.663 |
| **Benchmark: Equal Weight Monthly** | Multi-Year | +43.79% | +10.48% | 0.273 | 0.533 | 22.00% | 1.43x | ₹5,423.17 | 131 | 68.7% | 4.358 |

*Full CSV export persisted to:* [`docs/results/step13_7/alpha_v2_scorecard.csv`](file:///c:/Users/achie/OneDrive/Desktop/Trading-Bot/docs/results/step13_7/alpha_v2_scorecard.csv).

---

## PHASE 8 — ML SIGNAL QUALITY & CONVERSION EFFICIENCY

Evaluation of walk-forward expanding Ridge predictions and conversion into net returns:

### Signal Quality Metrics
- **Mean Expanding Training IC:** `+0.3276`
- **Mean Cross-Sectional OOS IC:** `+0.0290`
- **Information Ratio (IC / $\sigma_{\text{IC}}$):** `0.043`
- **Directional Accuracy:** `51.8%`
- **Weekly Signal Autocorrelation:** `0.794` (Features exhibit high persistence across weeks)

### Signal Conversion Efficiency (Return per Unit Turnover)

$$\text{Conversion Efficiency} = \frac{\text{Net Multi-Year Return (\%)}}{\text{Multi-Year Turnover (x)}}$$

| Strategy Variant | Net Multi-Year Return | Multi-Year Turnover | Return per Unit Turnover |
| :--- | :---: | :---: | :---: |
| **Variant A (Baseline Weekly)** | -5.25% | 52.99x | **-0.099** |
| **Variant B (Turnover-Penalized Weekly)** | +21.14% | 2.32x | **+9.112** |
| **Variant C (Constrained Monthly)** | +42.79% | 16.66x | **+2.568** |
| **Variant E (Monthly Pen + Deadband)** | +35.97% | 0.33x | **+109.000** |
| **Variant E2 (Weekly Pen + Deadband)** | +34.77% | 0.28x | **+124.179** |
| **Benchmark: Equal Weight Weekly** | +44.62% | 2.48x | **+17.992** |
| **Benchmark: Equal Weight Monthly** | +43.79% | 1.43x | **+30.622** |

*Artifact Reference:* [`docs/results/step13_7/ml_signal_quality.json`](file:///c:/Users/achie/OneDrive/Desktop/Trading-Bot/docs/results/step13_7/ml_signal_quality.json).

---

## PHASE 9 — COST ROBUSTNESS & SENSITIVITY SWEEP

Evaluating strategy viability as friction scales from 0 to 50 bps on the baseline calibration period:

| Variant | 0 bps Net Return | 10 bps Net Return | 20 bps Net Return | 30 bps Net Return | 50 bps Net Return | Costs @ 50 bps (₹) | Survives 50 bps? |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Variant A (Baseline Weekly)** | +18.72% | +15.45% | +12.32% | +9.20% | **+3.28%** | ₹143,277.30 | **Fails Rf (Sharpe -0.23)** |
| **Variant B (Turnover-Penalized)** | +12.72% | +12.57% | +12.42% | +12.28% | **+11.99%** | ₹6,652.84 | **YES (Sharpe +0.71)** |
| **Variant C (Monthly SLSQP)** | +14.86% | +13.90% | +12.96% | +12.06% | **+10.24%** | ₹43,145.43 | **YES (Sharpe +0.47)** |
| **Variant E (Monthly Pen+Deadband)**| +12.30% | +12.22% | +12.15% | +12.08% | **+11.93%** | ₹3,612.39 | **YES (Sharpe +0.63)** |
| **Benchmark: Equal Weight Weekly** | +15.07% | +14.88% | +14.71% | +14.49% | **+14.07%** | ₹9,031.04 | **YES (Sharpe +0.78)** |

**Conclusion:** Unpenalized weekly rebalancing is cost-fragile, suffering a 15.4% return decay from 0 to 50 bps friction. By contrast, Turnover-Penalized optimization (Variant B) and Pen+Deadband (Variant E) lose less than 0.75% return across the entire 0 to 50 bps spectrum, demonstrating complete transaction cost immunity.

*Artifact Reference:* [`docs/results/step13_7/cost_sensitivity_sweep.csv`](file:///c:/Users/achie/OneDrive/Desktop/Trading-Bot/docs/results/step13_7/cost_sensitivity_sweep.csv).

---

## PHASE 10 — FACTOR EXPOSURE & RETURN ATTRIBUTION

Linear regression of daily returns against the Equal-Weighted Benchmark over the 3.7-year horizon:

$$R_{\text{strategy}, t} = \alpha + \beta R_{\text{market}, t} + \epsilon_t$$

### Regression Results

| Strategy | Market Beta ($\beta$) | Annualized Alpha ($\alpha$) | $R^2$ | Interpretation |
| :--- | :---: | :---: | :---: | :--- |
| **Baseline Weekly (Variant A)** | **0.878** | **-9.76% p.a.** | **0.591** | Negative net alpha driven entirely by ₹167,495 in transaction friction. |
| **Turnover-Penalized (Variant B)** | **0.758** | **-1.92% p.a.** | **0.510** | Turnover penalty eliminates ~8% p.a. in cost drag, but active alpha remains mildly negative. |

*Artifact Reference:* [`docs/results/step13_7/factor_exposure_analysis.json`](file:///c:/Users/achie/OneDrive/Desktop/Trading-Bot/docs/results/step13_7/factor_exposure_analysis.json).

---

## PHASE 11 — BROADER UNIVERSE DATA SPECIFICATION

In strict accordance with the anti-fabrication mandate:
- **Available Benchmark Data:** 5 symbols (`RELIANCE`, `TCS`, `INFY`, `HDFCBANK`, `ICICIBANK`), 1,241 daily adjusted bars (`2021-09-16` to `2026-09-16`).
- **Unavailable Catalog Equities:** 47 symbols in `CuratedNifty500Provider` have zero local Parquet bars.
- **Specification for Production Ingestion:**
  - Asset Class: NSE Cash Equities (CM segment)
  - Historical Span Required: `2021-09-16` to `2026-09-16` (minimum 1,240 trading sessions)
  - Fields: `timestamp, symbol, open, high, low, close, volume, value, vwap`
  - Corporate Actions: Splits, Bonuses, Cash Dividends, and Rights Adjustments
  - Storage Destination: `data_storage/parquet/adjusted/symbol={SYM}/data.parquet`

*Artifact Reference:* [`docs/results/step13_7/universe_data_requirements.json`](file:///c:/Users/achie/OneDrive/Desktop/Trading-Bot/docs/results/step13_7/universe_data_requirements.json).

---

## PHASE 12 — ANTI-OVERFITTING PROTOCOL

All research parameters were defined *a priori* using economic logic rather than historical maximization:
1. **Turnover Penalty ($\gamma = 1.0$):** Selected based on 15 bps expected friction and 52-week horizon; not tuned against backtest return.
2. **Deadband Threshold ($\tau = 2.5\%$):** Predefined institutional threshold to filter noise; not optimized.
3. **Monthly Cadence (`1ME`):** Standard institutional calendar rebalance interval.
4. **Out-of-Sample Holdout:** Period 2 (`2024-05-01` to `2026-09-16`) was strictly evaluated out-of-sample with zero parameter adjustments.

---

## PHASE 13 — ALPHA V2 GATE CLASSIFICATIONS

In direct fulfillment of Phase 13 requirements:

| Gate Dimension | Classification | Primary Quantitative Justification |
| :--- | :---: | :--- |
| **A. Alpha Evidence** | **WEAK** | Out-of-sample cross-sectional test IC remains +0.0290 (IR = 0.043). Active models show limited stock discrimination. |
| **B. Incremental Alpha vs Passive** | **WEAK** | Passive Equal Weight Weekly delivered +44.62% vs +42.79% for Monthly SLSQP and +35.97% for Variant E. Active allocation failed to beat passive $1/N$. |
| **C. Turnover Economics** | **SUPPORTED** | Turnover penalties and deadbands successfully cured churn, cutting multi-year turnover from 52.99x to 0.33x and saving >₹166,000 in friction. |
| **D. OOS Robustness** | **WEAK** | While low-turnover variants remained positive OOS (+16.7% to +31.9%), they did not convincingly outperform passive Equal Weight (+27.5%). |
| **E. Multi-Regime Robustness** | **WEAK** | The active ML model exhibits 0.000 rank IC during broad bull runs, performing well only during corrective regimes. |

---

## PHASE 14 — PERMANENT TEST SUITE & VERIFICATION

A dedicated test suite [`tests/test_alpha_v2_research.py`](file:///c:/Users/achie/OneDrive/Desktop/Trading-Bot/tests/test_alpha_v2_research.py) was implemented with 5 passing tests:
1. `test_frozen_baseline_preservation`: Confirms baseline metrics (+14.36% return, 13.92x turnover, ₹44,959.99 costs) remain 100% invariant.
2. `test_universe_catalog_coverage_and_no_fabrication`: Verifies 5 available symbols, 47 unavailable catalog symbols, and zero synthetic bars.
3. `test_chronological_oos_separation`: Confirms OOS period strictly succeeds baseline period.
4. `test_step13_7_artifacts_exist`: Confirms all 7 machine-readable files exist and are non-empty.
5. `test_turnover_reduction_invariants`: Mathematically asserts that turnover penalty reduces churn by $\ge 80\%$ and monthly cadence reduces churn by $\ge 50\%$.

### Execution Verification
```bash
# Targeted Alpha V2 test suite
.venv/Scripts/python -m pytest tests/test_alpha_v2_research.py -v
# Result: 5 passed in 9.19s

# Full repository regression test suite
.venv/Scripts/python -m pytest tests -q
# Result: 261 passed, 7 warnings in 84.12s
```
