# APEX QUANT — NIFTY 500 Universe Management Architecture

## 1. Executive Summary

The **Universe Management Subsystem** (`universe/`) governs the definition, historical tracking, and dynamic screening of the Indian equity investment universe for **APEX QUANT**.
Its central responsibility is to answer:
> *"Which stocks were officially tradeable and met all liquidity and risk criteria on date $T$?"*

By explicitly maintaining effective membership dates (`effective_from`, `effective_to`), the subsystem eliminates **survivorship bias** before feature engineering (Step 4) and ML ranking (Step 5).

---

## 2. Universe Architecture Diagram

```
┌────────────────────────────────────────────────────────┐
│               Curated NIFTY 500 Provider               │
│     (Historical Additions, Removals, and Mergers)      │
└───────────────────────────┬────────────────────────────┘
                            │ Point-in-Time Reconstitution
                            ▼
┌────────────────────────────────────────────────────────┐
│             Nifty500 Repository Engine                 │
│         (universe/models.py & nifty500.py)             │
│    Reconstructs exact constituent roster on date T     │
└───────────────────────────┬────────────────────────────┘
                            │ Raw Constituents Snapshot
                            ▼
┌────────────────────────────────────────────────────────┐
│            Historical Market Data Ingestion            │
│   (Step 2 Parquet: data strictly <= date T, no leak)   │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│              Stock Filter Pipeline Engine              │
│               (universe/stock_filter.py)               │
│                                                        │
│  ├── 1. ListingStatusFilter  (Exclude delisted/halted) │
│  ├── 2. PriceFilter          (Min price >= ₹10.0)      │
│  ├── 3. LiquidityFilter      (Median turnover >= ₹5 Cr)│
│  ├── 4. HistoryFilter        (Min 60 trading bars)     │
│  └── 5. DataQualityFilter    (Max 5% missing sessions) │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│               Eligible Tradeable Universe              │
│    (Stock Candidates + Itemized Diagnostic Reasons)    │
│                           │                            │
│   ──▶ Ready for Step 4 Feature Engineering & ML        │
└────────────────────────────────────────────────────────┘
```

---

## 3. Core Domain Models

| Model | File | Description |
| :--- | :--- | :--- |
| `Stock` | `universe/models.py` | Canonical equity model (`symbol`, `company_name`, `isin`, `sector`, `industry`, `listing_status`). |
| `UniverseMembership` | `universe/models.py` | Effective date bounds (`effective_from`, `effective_to`) ensuring point-in-time reconstruction. |
| `UniverseSnapshot` | `universe/models.py` | Immutable catalog of constituents active on evaluation date $T$. |
| `EligibilityResult` | `universe/models.py` | Audit record detailing whether a stock passed, along with explicit rejection reason codes. |
| `SectorCategory` | `universe/sector.py` | 11 official NSE sector categories (Financials, IT, Energy, FMCG, Auto, Pharma, etc.). |
| `LiquidityMetrics` | `universe/liquidity.py` | 20-day median turnover, average turnover, and valid session continuity. |

---

## 4. Screening Pipeline & Filter Taxonomy

Rejections are never opaque. Every screened equity produces an explicit `EligibilityResult` with exact reason codes:

```python
pipeline = StockFilterPipeline([
    ListingStatusFilter(),                               # Rejects if DELISTED or SUSPENDED
    PriceFilter(min_price=10.0),                         # Rejects if close < ₹10.0
    LiquidityFilter(min_median_turnover=50_000_000.0),   # Rejects if 20d median turnover < ₹5 Cr
    HistoryFilter(min_history_bars=60),                  # Rejects if history < 60 trading days
    DataQualityFilter(max_missing_pct=0.05),             # Rejects if > 5% missing trading days
])
```

### Diagnostic Reason Codes:
- `stock_delisted`: Company was delisted on or prior to the evaluation date.
- `stock_suspended`: Trading was halted or suspended by the exchange.
- `price_below_minimum`: Closing price fell below ₹10 (penny stock filter).
- `median_turnover_below_threshold`: 20-day rolling median daily turnover fell below ₹5 Crore.
- `insufficient_history`: Fewer than 60 historical trading bars available prior to date $T$.
- `missing_data_exceeds_threshold`: Missing trading sessions exceeded 5% in the lookback window.
- `no_price_data`: No historical market data was found for this symbol.

---

## 5. Integration with Step 2 Market Data

The universe layer consumes Step 2 columnar Parquet storage directly:
```python
# Zero Lookahead Query:
data_df = storage.query_by_symbol(stock.symbol, end_date=as_of_date, is_adjusted=True)
```
- Only bars completed on or before `as_of_date` are passed to filters.
- Zero future bars or future corporate action events are visible to the screener.

---

## 6. CLI Usage

To inspect the point-in-time universe and view screening diagnostics for any date:
```bash
python -m universe.universe_manager --date 2024-01-15 --min-price 10.0 --min-turnover 50000000
```
