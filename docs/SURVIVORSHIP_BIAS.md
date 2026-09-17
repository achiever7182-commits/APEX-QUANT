# APEX QUANT — Survivorship Bias Protection & Point-in-Time Universe Architecture

## 1. What is Survivorship Bias?

**Survivorship bias** occurs when a backtesting or machine learning system evaluates a trading strategy on a universe of stocks that is defined using today's constituent list rather than the constituents that actually existed at each point in time.

### The Problem:
- In 2026, the NIFTY 500 consists of companies that have succeeded, grown, or survived.
- If we simulate a trading strategy starting in 2018 using the 2026 NIFTY 500 list, we implicitly grant our model **divine prescience**: the model will only select companies that were destined to survive for the next 8 years.
- Companies that went bankrupt, faced insolvency, were delisted, or collapsed (e.g., DHFL, Reliance Communications, Yes Bank during its restructuring) are artificially excluded from the backtest, falsely inflating strategy Sharpe ratios, win rates, and annualized returns.

---

## 2. APEX QUANT Architectural Solution

APEX QUANT eliminates survivorship bias through **Point-in-Time Universe Reconstruction**:

### A. Explicit Membership Spans
Every stock in the universe database is indexed with chronological validity bounds:
- `effective_from`: Date the company was added to the universe/index.
- `effective_to`: Date the company was removed, delisted, or acquired (or `None` if currently active).

```python
# Example: HDFCLTD was an active NIFTY constituent until its merger on July 13, 2023:
UniverseMembership(
    symbol="HDFCLTD",
    universe_name="NIFTY500",
    effective_from=date(2020, 1, 1),
    effective_to=date(2023, 7, 12),
)

# JIOFIN entered the universe following its demerger on August 21, 2023:
UniverseMembership(
    symbol="JIOFIN",
    universe_name="NIFTY500",
    effective_from=date(2023, 8, 21),
    effective_to=None,
)
```

### B. Point-in-Time Query Contract
When the backtester steps to date $T$, it invokes:
```python
snapshot = universe_manager.get_universe(date=T)
```
- A query on `2023-01-15` returns `HDFCLTD` as an active constituent and **excludes** `JIOFIN`.
- A query on `2024-01-15` returns `JIOFIN` and **excludes** `HDFCLTD`.

---

## 3. Survivorship Status Reporting (`PointInTimeStatus`)

Not all historical datasets have complete reconstitution records. Rather than pretending partial data is bias-free, the universe manager explicitly exports its integrity state:

1. **`POINT_IN_TIME_COMPLETE`**:
   - Reconstitution history, additions, removals, and delisting dates are fully tracked.
   - Strategy backtests run under this status are considered realistic and institutionally sound.

2. **`POINT_IN_TIME_INCOMPLETE`**:
   - The universe list is static or partial.
   - The backtesting engine is programmed to display clear warning banners indicating potential survivorship bias.

---

## 4. Handling Delistings and Corporate Amalgamations

When a holding undergoes a delisting or merger event:
1. `ListingStatusFilter` detects `ListingStatus.DELISTED` on `delisting_date` and blocks further purchases.
2. Existing positions are marked for orderly liquidation or cash reconciliation at the terminal price.
3. The strategy never suffers from phantom holdings that continue trading after an official delisting.

---

## 5. Data Integrity Best Practices for Future Stages

1. **Never Backtest with Static Lists**:
   Always pass `as_of_date` when querying universe membership.
2. **Never Look Ahead for Turnover**:
   Liquidity metrics must only compute rolling statistics over bars completed on or before date $T$.
3. **Audit Ineligible Equities**:
   Review rejection reasons emitted by `EligibilityResult` to ensure valid stocks are not mistakenly filtered due to minor data gaps.
