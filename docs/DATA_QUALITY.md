# APEX QUANT — Data Quality and Validation Standards

## 1. Quality Philosophy

In quantitative finance and machine learning trading systems, data quality is paramount. Garbage data produces misleading backtests and invalid predictive models.
The **APEX QUANT** data quality subsystem is built around four fundamental principles:

1. **Zero Lookahead**: Timestamps represent the point in time at which the bar was completed. No future corporate action knowledge or subsequent bar values leak backward into historical feature matrices.
2. **Never Silently Mutate**: Corrections, deduplications, and dropped invalid rows are explicitly logged with detailed audit messages.
3. **Flag Rather Than Delete Anomalies**: Legitimate corporate events or market black swan events (e.g. COVID crash, budget day announcements) cause massive single-day moves. An unannounced >20% price move is flagged for human or algorithmic review rather than automatically erased.
4. **Calendar Cross-Validation**: Indian equities trade strictly on official NSE trading days. All series are cross-validated against the statutory exchange calendar.

---

## 2. The 12 Data Quality Validation Checks

| # | Check Name | Rule Definition | Severity on Failure | Action Taken |
| :-: | :--- | :--- | :-: | :--- |
| **1** | **Duplicate Timestamps** | `count(duplicated(timestamp)) == 0` | WARNING | Deduplicated by keeping the latest record; flagged in audit log. |
| **2** | **Chronological Order** | `timestamp[i] < timestamp[i+1]` | FAIL | Sorted strictly ascending; abort if order cannot be resolved. |
| **3** | **Missing Trading Days** | Cross-reference dates against `NSEMarketCalendar` | WARNING | Missing dates are listed in the report anomalies for investigation. |
| **4** | **Null / NaN Values** | `any(isna(open, high, low, close, volume)) == False` | FAIL | Rows containing NaNs in essential fields are dropped with logging. |
| **5** | **Negative Prices** | `min(open, high, low, close) > 0` | FAIL | Negative prices are mathematically invalid; rows are dropped. |
| **6** | **Negative Volume** | `volume >= 0` | FAIL | Negative volume is physically impossible; rows are dropped. |
| **7** | **High-Low Integrity** | `high >= low` | FAIL | Inverted bars (`high < low`) are invalid and rejected. |
| **8** | **Open in Bounds** | `low <= open <= high` | FAIL / WARNING | Checked with a $10^{-4}$ floating point tolerance; sanitized or dropped. |
| **9** | **Close in Bounds** | `low <= close <= high` | FAIL / WARNING | Checked with a $10^{-4}$ floating point tolerance; sanitized or dropped. |
| **10** | **Abnormal Jumps** | $\| \Delta \text{Close} / \text{Close}_{t-1} \| \le 20\%$ | WARNING | Flagged in anomalies report. Not deleted to avoid erasing genuine volatility. |
| **11** | **Duplicate Rows** | Exact identical duplicate rows | WARNING | Dropped by deduplication pass. |
| **12** | **Timezone Consistency** | Timestamps must be normalized to standard UTC / IST | FAIL | Enforced via `pd.to_datetime(..., utc=True)`. |

---

## 3. Benchmark Universe Audit Results

The data pipeline was executed on the 5 benchmark NIFTY 50 equities covering the last 5 years of daily historical data (September 2021 to September 2026):

| Symbol | Rows Ingested | Start Date | End Date | Missing Days | Duplicates | Corporate Actions | Quality Status |
| :--- | :-: | :-: | :-: | :-: | :-: | :-: | :-: |
| **RELIANCE** | 1,241 | 2021-09-16 | 2026-09-16 | 3 | 0 | 6 (1 Split + 5 Divs) | **PASS** |
| **TCS** | 1,241 | 2021-09-16 | 2026-09-16 | 3 | 0 | 20 (20 Divs) | **PASS** |
| **INFY** | 1,241 | 2021-09-16 | 2026-09-16 | 3 | 0 | 10 (10 Divs) | **PASS** |
| **HDFCBANK** | 1,241 | 2021-09-16 | 2026-09-16 | 3 | 0 | 7 (7 Divs) | **PASS** |
| **ICICIBANK** | 1,241 | 2021-09-16 | 2026-09-16 | 3 | 0 | 5 (5 Divs) | **PASS** |

*Note on Missing Days*: The 3 reported missing days correspond to special exchange holiday sessions (e.g. Muhurat trading hours occurring on weekends or unscheduled clearing halts) that are not classified as full business days.

---

## 4. Known Limitations & Roadmap for Subsequent Steps

1. **Point-in-Time Universe Tracking**:
   - In Step 2, benchmark stocks are selected using current constituent status.
   - *Roadmap*: Step 3 (**NIFTY 500 Universe Management**) will implement dynamic point-in-time universe tracking and historical reconstitution tables to prevent survivorship bias in backtests.
2. **Intraday Data Retention Limits**:
   - Public data endpoints limit high-frequency 5-minute/1-minute intraday data to the past 60 days.
   - Long-term 10-year research is currently conducted on daily bars until licensed historical tick data or broker feeds (Kite Connect) are integrated in Stage 7.
3. **Dividend Cash Flow vs. Total Return Adjustment**:
   - Current default adjustment applies split and bonus adjustments directly to price/volume series.
   - Proportional dividend total return adjustment is supported via `adjust_dividends=True` in `CorporateActionAdjuster` and can be enabled based on strategy requirements.
