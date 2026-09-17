# APEX QUANT — Feature Engineering Architecture & Specification

## 1. Overview & Objectives

The **Multi-Stock Feature Engineering Subsystem** (`features/`) transforms historical and point-in-time market data into a structured, zero-lookahead, ML-ready cross-sectional dataset. It serves as the foundational bridge between market data storage/universe definitions and downstream machine-learning models, stock ranking, and risk allocation.

```
Market Data (Parquet Storage)
            ↓
Universe Selection (Point-in-Time NIFTY500 Curated Sample)
            ↓
Feature Engine (features/)
  ├── Price Features (Returns, Log Returns, Gap, Location)
  ├── Trend Features (SMAs, EMAs, Price/MA Ratios, Spreads)
  ├── Momentum Features (Wilder's RSI, ROC, Normalized Momentum, Acceleration)
  ├── Volatility / Risk Features (Rolling Std, ATR, ATR %, Range, Downside Vol)
  ├── Volume / Liquidity Features (Volume Change, Volume MAs, Ratios, Turnover)
  ├── Relative Strength Features (Stock vs Benchmark Excess Returns)
  └── Market Regime Features (Macro Trend, Benchmark Volatility, Market State)
            ↓
Data Quality Validation (Duplicate, Inf, Bounds, Monotonicity Checks)
            ↓
Optional Cross-Sectional Normalization (Z-Score, Rank, Winsorization per Timestamp)
            ↓
Cross-Sectional Dataset Panel [timestamp, symbol, feature_1, ..., feature_k]
```

---

## 2. Point-in-Time Safety & Leakage Rules

> [!IMPORTANT]
> **Strict Zero-Lookahead Invariant**:
> For any observation evaluated at calendar date or timestamp $t$, all computations are strictly restricted to observations $\le t$. Future prices, volume, universe membership, or benchmark returns ($> t$) are mathematically excluded.

### Anti-Leakage Guardrails Implemented:
1. **Right-Aligned Rolling Windows**: All moving averages, standard deviations, and rolling extremes use right-aligned windows (`closed="right"`).
2. **Lagged Ratio Operations**: Price returns and momentum use explicit backward shifts ($P_t / P_{t-k} - 1$).
3. **No Centered Smoothing**: Centered moving averages and bidirectional filters (e.g. Savitzky-Golay) are strictly prohibited.
4. **Independent Cross-Sectional Slices**: Cross-sectional transformations (z-scores, percentile ranks, winsorization) are computed **strictly grouped by timestamp** (`groupby("timestamp")`). Normalization parameters (mean $\mu_t$, standard deviation $\sigma_t$) are computed solely from active universe instruments at timestamp $t$. Data from $t+1$ or $t-1$ never contaminates timestamp $t$.
5. **Leakage Audit Verification**: Automated regression tests deliberately alter future rows ($t+1 \dots T$) and verify that historical feature vectors at $t$ remain identical to machine precision.

---

## 3. Feature Definitions & Mathematical Formulations

### A. Price Features (`features/price.py`)
- **Multi-Period Simple Return**:
  $$R_{k,t} = \frac{P_t}{P_{t-k}} - 1 \quad \text{for } k \in \{1, 3, 5, 10, 20, 60\}$$
- **1-Day Log Return**:
  $$r_{1,t} = \ln\left(\frac{P_t}{P_{t-1}}\right)$$
- **Overnight Gap Return**:
  $$\text{Gap}_t = \frac{\text{Open}_t - \text{Close}_{t-1}}{\text{Close}_{t-1}}$$
- **Price Channel Location (20-day)**:
  $$\text{Loc}_{20,t} = \frac{P_t - \min_{i \in [0, 19]} L_{t-i}}{\max_{i \in [0, 19]} H_{t-i} - \min_{i \in [0, 19]} L_{t-i} + \epsilon} \in [0, 1]$$

### B. Trend Features (`features/trend.py`)
- **Simple Moving Averages (SMA)**:
  $$\text{SMA}_{k,t} = \frac{1}{k}\sum_{i=0}^{k-1} P_{t-i} \quad \text{for } k \in \{5, 10, 20, 50, 100, 200\}$$
- **Price-to-SMA Ratio**:
  $$\text{Ratio}_{\text{SMA},k,t} = \frac{P_t}{\text{SMA}_{k,t}} - 1$$
- **Exponential Moving Averages (EMA)**:
  $$\text{EMA}_{k,t} = \alpha P_t + (1 - \alpha)\text{EMA}_{k,t-1}, \quad \alpha = \frac{2}{k+1} \quad \text{for } k \in \{9, 21, 50\}$$
- **Moving Average Spreads**:
  $$\text{Spread}_{\text{EMA},9,21} = \frac{\text{EMA}_{9,t}}{\text{EMA}_{21,t}} - 1, \quad \text{Spread}_{\text{SMA},20,50} = \frac{\text{SMA}_{20,t}}{\text{SMA}_{50,t}} - 1$$

### C. Momentum Features (`features/momentum.py`)
- **Wilder's Relative Strength Index (RSI 14)**:
  $$\text{RSI}_t = 100 - \frac{100}{1 + \text{RS}_t}, \quad \text{RS}_t = \frac{\text{EMA}_{\text{Wilder}}(\text{Gain}, 14)}{\text{EMA}_{\text{Wilder}}(\text{Loss}, 14) + \epsilon} \in [0, 100]$$
- **RSI Momentum (5-day)**:
  $$\Delta\text{RSI}_{5,t} = \text{RSI}_t - \text{RSI}_{t-5}$$
- **Rate of Change (ROC %)**:
  $$\text{ROC}_{k,t} = \frac{P_t - P_{t-k}}{P_{t-k}} \times 100 \quad \text{for } k \in \{5, 10, 20, 60\}$$
- **Normalized Momentum**:
  $$\text{MomNorm}_{k,t} = \frac{P_t - P_{t-k}}{P_t} \quad \text{for } k \in \{5, 10, 20, 60\}$$
- **Return Acceleration**:
  $$\text{Acc}_{5,t} = R_{5,t} - R_{5,t-5}$$

### D. Volatility & Risk Features (`features/volatility.py`)
- **Rolling Return Volatility**:
  $$\sigma_{k,t} = \sqrt{\frac{1}{k-1}\sum_{i=0}^{k-1}(R_{1,t-i} - \bar{R})^2} \quad \text{for } k \in \{10, 20, 60\}$$
- **Average True Range (ATR 14)**:
  $$\text{TR}_t = \max(H_t - L_t, |H_t - C_{t-1}|, |L_t - C_{t-1}|), \quad \text{ATR}_{14,t} = \text{EMA}_{\text{Wilder}}(\text{TR}, 14)$$
- **ATR Percentage**:
  $$\text{ATR}_{\%,t} = \frac{\text{ATR}_{14,t}}{C_t} \times 100$$
- **Daily Candle Range**:
  $$\text{Range}_{\%,t} = \frac{H_t - L_t}{C_t} \times 100$$
- **Downside Volatility (20-day Semi-Deviation)**:
  $$\sigma_{\text{down},20,t} = \sqrt{\frac{1}{20}\sum_{i=0}^{19}(\min(R_{1,t-i}, 0))^2}$$

### E. Volume Features (`features/volume.py`)
- **Volume Change**:
  $$\Delta V_t = \frac{V_t}{V_{t-1}} - 1$$
- **Volume Moving Averages & Ratio**:
  $$\text{SMA}_{V,k,t} = \frac{1}{k}\sum_{i=0}^{k-1}V_{t-i}, \quad \text{Ratio}_{V,k,t} = \frac{V_t}{\text{SMA}_{V,k,t}}$$
- **Estimated Daily Turnover**:
  $$\text{Turnover}_t = C_t \times V_t, \quad \text{TurnoverSMA}_{20,t} = \frac{1}{20}\sum_{i=0}^{19}\text{Turnover}_{t-i}$$

### F. Relative Strength vs Benchmark (`features/relative_strength.py`)
- **Relative Excess Return**:
  $$R_{\text{rel},k,t} = R_{\text{stock},k,t} - R_{\text{bench},k,t} \quad \text{for } k \in \{5, 20, 60\}$$
- **Benchmark Ratio & Trend**:
  $$\text{Ratio}_{\text{bench},t} = \frac{P_{\text{stock},t}}{P_{\text{bench},t}}, \quad \Delta\text{Ratio}_{20,t} = \frac{\text{Ratio}_t - \text{Ratio}_{t-20}}{\text{Ratio}_{t-20}} \times 100$$

### G. Market Regime Features (`features/market_regime.py`)
- **Benchmark Trend Flags**:
  - `regime_bench_above_sma50`: $\mathbf{1}(P_{\text{bench},t} > \text{SMA}_{50}(P_{\text{bench}})_t)$
  - `regime_bench_above_sma200`: $\mathbf{1}(P_{\text{bench},t} > \text{SMA}_{200}(P_{\text{bench}})_t)$
- **Benchmark 20d Return & Volatility**:
  - `regime_bench_return_20d`, `regime_bench_volatility_20d`
- **Market State Classification**:
  $$\text{State}_t = \begin{cases} +1 & \text{if } P_{\text{bench},t} > \text{SMA}_{50,t} \text{ and } R_{\text{bench},20,t} > 0 \text{ (Bullish)} \\ -1 & \text{if } P_{\text{bench},t} < \text{SMA}_{50,t} \text{ and } R_{\text{bench},20,t} < 0 \text{ (Bearish)} \\ 0 & \text{otherwise (Neutral)} \end{cases}$$

---

## 4. Adjusted vs Raw Price Policy

To maintain quantitative integrity across corporate actions:
- **Adjusted Prices (`is_adjusted=True`)**: Used for all return, moving average, oscillator, momentum, and relative strength calculations. This prevents artificial return spikes or trend breakdowns caused by stock splits, reverse splits, or large cash dividends.
- **Raw Volume (`volume`)**: Used for liquidity and traded share volume metrics.
- **Turnover**: Computed as $Close_{\text{adj}} \times Volume$ as an effective trading-value proxy.

---

## 5. Benchmark Architecture

The benchmark architecture supports three interchangeable sources via `BenchmarkProvider`:
1. **Explicit Index Symbol**: Directly loaded from Parquet storage (e.g. `^NSEI` or `NIFTY50`).
2. **Synthetic Equal-Weighted Basket**: Constructed dynamically by aggregating available benchmark equities (`RELIANCE`, `TCS`, `INFY`, `HDFCBANK`, `ICICIBANK`). Daily benchmark return is the arithmetic mean of active constituent returns.
3. **User-Supplied Series**: Any external benchmark series formatted with `['timestamp', 'close']`.

---

## 6. Missing Data & Warmup Policies

1. **Warmup Window**: Because technical indicators require historical lookback (e.g. 200 bars for SMA 200, 60 bars for 60d return), initial bars naturally evaluate to `NaN`.
2. **Zero Forward-Filling Across Invalid Dates**: The engine never silently forward-fills missing observations across non-trading holidays or extended trading suspensions.
3. **Explicit History Flags**:
   - `has_sufficient_history`: Set to `True` when bar index $\ge 60$ (minimum lookback for short/medium-term ML models).
   - `has_full_warmup`: Set to `True` when bar index $\ge 200$ (sufficient for 200-day moving average).
4. **Downstream Consumption**: Models in Step 5 filter on `has_sufficient_history == True` to guarantee clean inputs without NaN imputation artifacts.

---

## 7. Data Quality & Feature Validation

The `FeatureValidator` class audits all extracted panels against four failure modes:
- **Duplicate Rows**: Zero duplicate `(timestamp, symbol)` tuples permitted.
- **Monotonicity**: Timestamps per symbol must be strictly ascending.
- **Finite Check**: Zero `+inf` or `-inf` values permitted.
- **Domain Validity**:
  - RSI $\in [0, 100]$
  - ATR $\ge 0$
  - Volatilities $\ge 0$
  - Candle range $\% \ge 0$
  - Turnover $\ge 0$

---

## 8. Current System Limitations

1. **Benchmark Proxy**: The current benchmark uses a synthetic equal-weighted composite of the 5 benchmark NIFTY stocks rather than an official NSE exchange feed for `^NSEI`. Once broad index data is ingested, `BenchmarkProvider` seamlessly switches to official NIFTY 50/500 data.
2. **Curated Universe**: The 5-stock benchmark dataset represents a developmental sample. Expansion to the full 500-stock index will occur during future production data ingestion.
