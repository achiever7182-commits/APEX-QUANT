# APEX QUANT — Indian Equity Market Data Architecture

## 1. System Overview

The **APEX QUANT** market data layer provides a production-grade, asset-agnostic historical and real-time market data foundation for Indian equities (NSE/BSE). It is engineered to scale seamlessly to the full **NIFTY 500** universe (and beyond) over 10+ years of daily and intraday history.

---

## 2. End-to-End Data Pipeline Flow

```
┌─────────────────────────┐
│   Data Provider API     │ (e.g. Yahoo Finance, Broker REST, NSE EOD)
└────────────┬────────────┘
             │ Raw OHLCV + Corporate Events (Splits/Dividends)
             ▼
┌─────────────────────────┐
│       RAW ARCHIVE       │ Written immutably to:
│     (Parquet Storage)   │ data_storage/parquet/raw/symbol=<SYM>/data.parquet
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ Corporate Action Engine │ Computes backward adjustment factors for splits/bonuses
│  (models.py & adjuster) │ (Preserves nominal returns without artificial price drops)
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│     DataNormalizer      │ Enforces canonical schema, numeric types,
│     (normalizer.py)     │ ascending chronological sort, and deduplication
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│  DataQualityValidator   │ Executes 12 financial and mathematical sanity checks
│     (validator.py)      │ Cross-references official NSEMarketCalendar
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│    PROCESSED ARCHIVE    │ Partitioned columnar storage:
│   (Adjusted Parquet)    │ data_storage/parquet/adjusted/symbol=<SYM>/data.parquet
└─────────────────────────┘
```

---

## 3. Core Design Principles

1. **Strict Separation of Raw and Processed Data**:
   - Raw source data is stored immediately upon download in `data_storage/parquet/raw/`.
   - Raw files are **never modified or overwritten** with adjusted numbers.
   - All corporate action adjustments and cleanups are written to `data_storage/parquet/adjusted/`.
   - The entire pipeline is 100% deterministic and reproducible from raw files.

2. **Asset and Provider Agnostic**:
   - Internal instruments use canonical uppercase symbols (`RELIANCE`, `TCS`, `INFY`, `HDFCBANK`, `ICICIBANK`).
   - Exchange suffixes (`.NS`, `.BO`) are encapsulated within provider adapters.
   - The storage, normalization, validation, and strategy layers have zero coupling to any external vendor or URL.

3. **Deterministic Corporate Actions Adjustment**:
   - A 1:10 stock split or 1:1 bonus issue will cut historical nominal prices in half or by ten. Without proper backward adjustment, ML algorithms and technical indicators would register an artificial catastrophic crash.
   - Historical prices prior to the `ex_date` are divided by the split multiplier ($P_{adj} = P_{raw} / \text{multiplier}$), and volumes are multiplied ($V_{adj} = V_{raw} \times \text{multiplier}$) so that nominal dollar turnover ($P \times V$) remains invariant.

4. **Columnar Parquet Storage**:
   - Built on `pyarrow` using Snappy compression.
   - Hive-style directory partitioning:
     ```
     data_storage/parquet/
     ├── raw/
     │   ├── symbol=RELIANCE/data.parquet
     │   └── symbol=TCS/data.parquet
     └── adjusted/
         ├── symbol=RELIANCE/data.parquet
         └── symbol=TCS/data.parquet
     ```
   - Enables fast cross-sectional panel queries across 500 stocks without loading unnecessary columns or rows into system RAM.

5. **Indian Market Calendar Integration**:
   - Aware of official NSE trading hours (09:15–15:30 IST) and statutory holidays (Republic Day, Diwali, Independence Day, etc. 2020–2026).
   - Abandons 24/7 continuous crypto market assumptions.

---

## 4. Module Map

| Module | File Path | Primary Responsibility |
| :--- | :--- | :--- |
| **Data Models** | `data/market/models.py` | `MarketBar` dataclass, canonical symbol formatting, conversion to legacy `Bar` interface. |
| **Market Calendar** | `data/market/calendar.py` | `NSEMarketCalendar` handling IST trading hours, session status, and statutory exchange holidays. |
| **Data Providers** | `data/market/provider.py` | `IMarketDataProvider` interface, `YahooFinanceProvider`, and deterministic `MockMarketDataProvider`. |
| **Corporate Actions** | `data/corporate_actions/` | `CorporateAction` models, disk cache loader, and `CorporateActionAdjuster` backward engine. |
| **Normalization** | `data/market/normalizer.py` | Schema standardization, deduplication, numeric coercion, and OHLC sanity checks. |
| **Quality Validator** | `data/market/validator.py` | 12 automated data-integrity checks and `DataQualityReport` generator. |
| **Parquet Storage** | `data/market/storage.py` | `ParquetMarketDataStorage` managing Hive partitions, date slicing, and cross-sectional queries. |
| **Ingestion Pipeline & CLI** | `data/market/loader.py` | End-to-end ingestion orchestrator and command-line entry point. |

---

## 5. How to Add Another Data Provider

To connect a new data source (e.g. Zerodha Kite Connect, Shoonya API, or a licensed EOD feed):
1. Subclass `IMarketDataProvider` in `data/market/provider.py`:
   ```python
   class KiteMarketDataProvider(IMarketDataProvider):
       def __init__(self, kite_client):
           self.client = kite_client

       def get_daily_bars(self, symbol: str, start_date=None, end_date=None) -> pd.DataFrame:
           # Fetch and return DataFrame with ['timestamp', 'open', 'high', 'low', 'close', 'volume']
           ...
       def get_corporate_actions(self, symbol: str, start_date=None, end_date=None) -> List[CorporateAction]:
           # Return list of CorporateAction objects
           ...
   ```
2. Pass the new provider instance to `MarketDataLoader(provider=KiteMarketDataProvider(...))`.
3. The rest of the pipeline (normalization, adjustment, validation, Parquet storage) operates without any modification.

---

## 6. How to Ingest Additional Stocks

To ingest any Indian stock from the command line:
```bash
# Ingest single stock
python -m data.market.loader --symbol TATAMOTORS

# Ingest with specific date range
python -m data.market.loader --symbol INFY --start 2022-01-01 --end 2024-12-31

# Check current storage inventory
python -m data.market.storage --status
```
