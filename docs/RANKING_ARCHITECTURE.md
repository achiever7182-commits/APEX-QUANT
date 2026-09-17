# APEX QUANT — Cross-Sectional Stock Ranking & Opportunity Engine

## 1. Overview & Architecture Philosophy

The **Cross-Sectional Stock Ranking & Opportunity Engine** (`ranking/`) converts empirical machine-learning forecasts (Step 5), multi-factor market features (Step 4), and point-in-time universe definitions (Step 3) into an orderly, deterministic, and risk-adjusted ranked list of equity opportunities.

```
Step 5 ML Forecasts (Predicted Returns) + Step 4 Multi-Factor Panel
                                ↓
        Point-in-Time Universe & Eligibility Filtering (ranking/filters.py)
                                ↓
        Cross-Sectional Sub-Score Normalization (ranking/scoring.py)
            ├── Prediction Score (35%)
            ├── Risk-Adjusted Score (20%)
            ├── Relative Strength Score (15%)
            ├── Momentum Score (10%)
            ├── Trend Score (10%)
            ├── Market Regime Score (5%)
            └── Liquidity Score (5%)
                                ↓
        Composite Opportunity Score Calculation (Weighted Linear Sum in [0, 1])
                                ↓
        Deterministic Tie-Breaking & Rank Assignment (ranking/ranker.py)
                                ↓
        Ranked Universe Output (Forwarded to Step 7 Portfolio Construction)
```

---

## 2. Universe Scope & Benchmark Terminology Clarifications

### A. Universe Scope Distinction
To ensure absolute precision and avoid misleading claims:
1. **52-Stock Curated Universe Catalog**: Maintained by `CuratedNifty500Provider` (Step 3) with reconstitution effective dates (`POINT_IN_TIME_SAMPLE`).
2. **5-Stock Empirical Test Dataset**: Real-data empirical validation performed in Step 6 uses the 5-stock benchmark dataset (`RELIANCE`, `TCS`, `INFY`, `HDFCBANK`, `ICICIBANK`).
3. **Full 500-Stock Ingestion**: The complete NIFTY 500 universe data ingestion and scaling is deferred to future production steps.

> [!IMPORTANT]
> Step 6 ranking performance has been empirically validated **ONLY on the 5-stock benchmark dataset**. It has not been validated on 52 or 500 stocks.

### B. Benchmark Terminology Distinction
1. **Synthetic Equal-Weighted Benchmark (Current)**: Relative strength and market regime features in Step 4 are currently calculated relative to a synthetic equal-weighted benchmark constructed from active assets in the database.
2. **Official NIFTY 500 Index Benchmark (Future)**: An official index feed (e.g., NIFTY 500 or NIFTY 50 index prices) will be integrated in subsequent milestones.
Step 6 factor scores and documentation explicitly refer to the synthetic benchmark, not an official index feed.

---

## 3. Eligibility Filtering & Diagnostics

Before ranking, every candidate asset must satisfy explicit quantitative eligibility criteria. Ineligible stocks are never silently dropped; they receive an explicit `RejectionReason` code:

| Eligibility Rule | Condition | Failure Reason |
| :--- | :--- | :--- |
| **Point-in-Time Universe** | Must be active constituent on evaluation date $t$ | `NOT_IN_UNIVERSE` |
| **Listing Status** | Must not be delisted on or prior to date $t$ | `DELISTED` |
| **Price Validity** | Close price must be finite, non-null, and $> 0$ | `INVALID_PRICE` |
| **Warmup Sufficiency** | Must have `has_sufficient_history == True` ($\ge 60$ bars) | `INSUFFICIENT_HISTORY` |
| **Prediction Availability** | Must possess finite non-null predicted return $\hat{y}$ | `MISSING_PREDICTION` |
| **Liquidity Threshold** | 20d Turnover $\ge \text{min\_median\_turnover}$ (if configured) | `LOW_LIQUIDITY` |
| **Volatility Ceiling** | 20d Volatility $\le \text{max\_volatility}$ (if configured) | `HIGH_VOLATILITY` |
| **Score Threshold** | Opportunity score $\ge \text{min\_opportunity\_score}$ (if configured) | `BELOW_SCORE_THRESHOLD` |

---

## 4. Opportunity Score Formulation & Factor Components

The **Composite Opportunity Score** is formulated as a weighted linear combination of normalized factor sub-scores:
$$\text{Opportunity Score} = \sum_{i=1}^{7} w_i \cdot S_i \in [0.0, 1.0]$$

### Factor Sub-Scores & Default Weights:

1. **Prediction Score ($w_1 = 0.35$)**:
   - Cross-sectional percentile rank of the forward return forecast $\hat{y}_t$ from the Step 5 model.
2. **Risk-Adjusted Score ($w_2 = 0.20$)**:
   - Reward-to-risk ratio:
     $$\text{Ratio}_s = \frac{\hat{y}_{s,t}}{\sigma_{20d, s, t} + \epsilon}$$
   - Normalized cross-sectionally. Safely clips extreme values ($[-50.0, +50.0]$) and handles near-zero volatility ($\epsilon = 10^{-6}$, vol floor $10^{-4}$).
3. **Relative Strength Score ($w_3 = 0.15$)**:
   - Cross-sectional percentile rank of 20-day excess return over the synthetic equal-weighted benchmark ($R_{\text{stock}, 20d} - R_{\text{bench}, 20d}$).
4. **Momentum Score ($w_4 = 0.10$)**:
   - Equal-weighted blend of normalized Wilder's RSI (14d), Rate of Change (20d), and normalized momentum.
5. **Trend Score ($w_5 = 0.10$)**:
   - Equal-weighted blend of normalized price-to-SMA 20 ratio ($P_t / \text{SMA}_{20,t} - 1$) and moving average spread ($\text{SMA}_{20,t} / \text{SMA}_{50,t} - 1$).
6. **Market Regime Score ($w_6 = 0.05$)**:
   - Macro state derived from the synthetic benchmark moving averages:
     $$\text{Score}_{\text{regime}} = \begin{cases} 1.0 & \text{if Bullish (+1)} \\ 0.5 & \text{if Neutral (0)} \\ 0.0 & \text{if Bearish (-1)} \end{cases}$$
7. **Liquidity Score ($w_7 = 0.05$)**:
   - Cross-sectional percentile rank of 20-day turnover ($Close \times Volume$).

---

## 5. Normalization Architecture

To prevent raw indicators with large numerical variances from dominating scores:
- **Percentile Rank Normalization (Default)**:
  Transforms raw values into uniformly distributed scores in $[0.0, 1.0]$ using `rank(pct=True, method="average")`.
- **Cross-Sectional Z-Score (Alternative)**:
  Standardizes values to zero mean and unit variance per timestamp slice:
  $$z_{s,t} = \frac{x_{s,t} - \mu_t}{\sigma_t + 10^{-8}}$$
- **Strict Timestamp Grouping**: Normalization parameters are evaluated strictly across the assets present at calendar date $t$. Observations from $t+1$ or $t-1$ never leak into timestamp $t$.

---

## 6. Deterministic Tie-Breaking Rules

To ensure 100% reproducible rank assignments across platforms and executions, the ranker enforces a 3-tier deterministic ordering hierarchy:
1. **Primary**: `opportunity_score` descending (highest score $\to$ Rank 1).
2. **Secondary**: `predicted_return` descending (higher expected return breaks score ties).
3. **Tertiary**: `symbol` ascending (alphabetical order, e.g. `'HDFCBANK'` before `'ICICIBANK'`).

---

## 7. Diagnostics & Historical Walk-Forward Validation

### A. Diagnostic Metrics
1. **Spearman Information Coefficient (IC)**: Rank correlation between Opportunity Score and realized forward return.
2. **Score Separation**: Difference in opportunity score between top-ranked eligible asset and bottom-ranked eligible asset:
   $$\text{Score Separation} = \text{Score}_{\text{top}} - \text{Score}_{\text{bottom}}$$
3. **Top-Bottom Forward Return Spread**: Realized forward return difference between the top-ranked asset and bottom-ranked asset:
   $$\text{Spread} = R_{\text{forward}, \text{top}} - R_{\text{forward}, \text{bottom}}$$
4. **Historical Return Correlation Matrix**: Pairwise correlation computed strictly using data $\le t$ (preparatory helper for Step 7).

### B. Multi-Date Walk-Forward Diagnostic Results (5-Stock Empirical Dataset)
Evaluated across 60 sequential trading sessions in Q1 2024:
- **Total Evaluated Sessions**: 60
- **Sample Count Per Session**: 5 stocks (`RELIANCE`, `TCS`, `INFY`, `HDFCBANK`, `ICICIBANK`)
- **Spearman IC Mean**: **+0.3653**
- **Spearman IC Median**: **+0.5000**
- **Spearman IC Standard Deviation**: **0.4003**
- **Spearman IC Hit Rate (IC > 0)**: **86.7%**
- **Mean Score Separation**: **0.5346**
- **Mean Top-Bottom Forward Return Spread**: **+3.79%**

### C. Side-by-Side Baseline Comparison
Evaluated on identical multi-date historical evaluation dates:

| Strategy / Model | IC Mean | IC Median | IC Std | IC Hit Rate | Top-Bottom Forward Return Spread |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Apex Composite** | **+0.3653** | **+0.5000** | **0.4003** | **86.7%** | **+3.79%** |
| Raw Prediction | +0.4383 | +0.5000 | 0.4309 | 86.7% | +4.29% |
| 20d Momentum | +0.1250 | +0.2000 | 0.4373 | 63.3% | +0.97% |
| Random Permutation | +0.0400 | +0.1000 | 0.5283 | 51.7% | -0.19% |

---

## 8. Anti-Leakage Invariants

> [!IMPORTANT]
> **Strict Zero-Lookahead Rule**:
> At evaluation date $T$, the ranker accesses only features, universe memberships, prices, volumes, and predictions derived on or before $T$. Future prices ($T+1 \dots$), future corporate actions, or future universe changes never alter historical rankings.
> This invariant is verified via automated tests in `tests/test_ranking.py::test_zero_lookahead_leakage_audit`.

---

## 9. Research Diagnostic Disclaimer

> [!CAUTION]
> **Research Diagnostics Only — No Profitability Guarantee**:
> The ranking engine produces relative cross-sectional orderings based on empirical statistical features and machine-learning forecasts. Ranks and Information Coefficients are research diagnostics evaluating sorting efficacy. They do NOT constitute proof of future profitability, investment returns, or production readiness. Realized trading performance depends on downstream portfolio construction (Step 7), transaction costs, slippage, and liquidity.
