# APEX-QUANT — Step 11: Real-Time Indian Market Data Infrastructure

## 1. Overview & Objective

Step 11 delivers a production-grade, modular, and fail-closed **Real-Time Indian Equity Market Data Infrastructure** for APEX-QUANT.
The system ingests real-time market quotes, normalizes vendor payloads into a canonical model (`NSE:SYMBOL`), executes rigorous data validation (sanity, non-negativity, relational OHLC invariants, timestamp sanity), detects feed staleness using the production `NSEMarketCalendar`, enforces connection resilience with exponential backoff and bounded retry limits, maintains a thread-safe latest-quote cache with backward-overwrite protection, aggregates streaming ticks into discrete timeframe bars, and provides zero-lookahead historical-to-realtime buffer handoff for feature warm-up and continuous ML inference.

Crucially, Step 11 strictly adheres to the fail-closed safety boundary established in Step 10:
- **Zero real broker network orders.**
- **Zero real money at risk.**
- **Zero API credentials or secrets hardcoded.**
- **Downstream execution remains permanently locked to paper trading (`PAPER-ONLY`).**

---

## 2. Architecture & Data Flow

```
   Market Data Source (Mock / Kite Feed Stub)
                     │
                     ▼
          Symbol & Quote Normalizer
        (Canonical format: NSE:TICKER)
                     │
                     ▼
           Real-Time Data Validator
     (Price, volume, spread, OHLC, skew)
                     │
         ┌───────────┴───────────┐
         ▼                       ▼
 Feed Health Monitor    Latest Quote Cache
(Staleness, throughput) (Thread-safe, monotonically
                         advancing timestamp)
         │                       │
         └───────────┬───────────┘
                     ▼
          Realtime Bar Aggregator
    (Time-boundary aligned, discrete bars)
                     │
                     ▼
       Historical-Realtime Handoff
     (Rolling 200-bar warm-up buffer)
                     │
                     ▼
     Step 4 Feature Engine & Pipeline
                     │
                     ▼
        [Step 9/10 Paper Trading]
        (Real Orders STRICTLY Blocked)
```

---

## 3. Core Modules & Components

### 3.1 Domain Models (`data/realtime/models.py`)
- **`NormalizedSymbol`**: Strongly typed canonical symbol container. Ensures uppercase alphanumeric tickers and standardized exchange prefixes (`NSE:RELIANCE`, `BSE:TCS`). Strips extraneous extensions (`.NS`, `.BO`).
- **`RealtimeQuote`**: Normalized market quote dataclass holding `symbol`, `exchange`, `timestamp`, `last_price`, `bid`, `ask`, `volume`, `open`, `high`, `low`, `close`, `previous_close`, `provider_timestamp`, `received_timestamp`, `sequence_number`, `data_source`, and session metadata.
- **`ConnectionState` (Enum)**: `DISCONNECTED`, `CONNECTING`, `CONNECTED`, `DEGRADED`, `RECONNECTING`, `FAILED`.
- **`MarketSessionState` (Enum)**: `PRE_MARKET`, `REGULAR`, `POST_MARKET`, `CLOSED`, `WEEKEND`, `HOLIDAY`.
- **`AggregatedBar`**: Discrete timeframe OHLCV bar container with `start_time`, `end_time`, `interval_seconds`, and explicit `is_complete` flag.
- **`FeedHealthMetrics`**: Telemetry metrics tracker recording message volumes, validity, duplicates, drops, reconnects, and timestamps.

### 3.2 Normalization & Translation (`data/realtime/normalizer.py`)
- **`SymbolNormalizer`**: Bidirectional conversion between raw symbols (e.g. `RELIANCE`, `reliance.ns`, `NSE:RELIANCE`) and canonical `NSE:SYMBOL`.
- **`QuoteNormalizer`**: Translates vendor-specific dictionaries (e.g. Kite Ticker binary/json feeds, generic WebSocket packets) into standard `RealtimeQuote` dataclasses without fabricating missing data.

### 3.3 Data Validation (`data/realtime/validator.py`)
- **`RealtimeDataValidator`**: Multi-point validation pipeline:
  1. Canonical symbol syntax.
  2. Finite, positive, non-zero price (`last_price > 0`, non-NaN).
  3. Non-negative volume (`volume >= 0`).
  4. Timestamp sanity: non-null, valid datetime, clock skew tolerance check (rejects timestamps > reference time + 5.0s).
  5. Relational OHLC checks (`low <= open <= high`, `low <= close <= high`, `low <= high`).
  6. Bid/Ask spread consistency (`bid <= ask`, rejects crossed markets).
  7. Monotonic sequence number checks.

### 3.4 In-Memory Cache (`data/realtime/cache.py`)
- **`LatestQuoteCache`**: Thread-safe in-memory cache using `threading.RLock`.
- Guarantees backward-overwrite protection: incoming quotes with `timestamp < cached.timestamp` are rejected.
- Evaluates individual symbol staleness based on configurable time horizons.

### 3.5 Feed Health & Calendar Integration (`data/realtime/health.py`)
- **`FeedHealthMonitor`**: Real-time telemetry engine evaluating feed health, throughput, error rates, dropped frames, and symbol staleness.
- Integrates with `data/market/calendar.py` (`NSEMarketCalendar`) to accurately resolve exchange session state (`REGULAR`, `PRE_MARKET`, `POST_MARKET`, `CLOSED`, `WEEKEND`, `HOLIDAY`).

### 3.6 Connection Management (`data/realtime/reconnect.py`)
- **`ConnectionManager`**: Stateful connection controller enforcing exponential backoff:
  $$\text{Delay} = \min(\text{max\_delay}, \text{base\_delay} \times \text{multiplier}^{\text{attempt\_count}})$$
- Enforces fail-closed behavior by terminating retries and transitioning to `ConnectionState.FAILED` when `max_attempts` is reached.

### 3.7 Bar Aggregation (`data/realtime/bar_aggregator.py`)
- **`RealtimeBarAggregator`**: Accumulates streaming quotes into fixed-interval candlestick bars (e.g. 5-minute bars).
- Boundary-aligned to exchange clock (e.g. 09:15:00, 09:20:00).
- Marks active bars `is_complete = False`; automatically marks `is_complete = True` and finalizes the bar when a tick from the subsequent interval is received.
- Provides `to_market_bar()` static helper to emit standard `MarketBar` instances.

### 3.8 Buffer Handoff (`data/realtime/handoff.py`)
- **`HistoricalRealtimeHandoff`**: Seeds a rolling buffer (up to `max_buffer_size`) from historical Parquet or CSV data.
- Appends completed real-time aggregated bars with boundary deduplication.
- Ensures zero lookahead leakage and emits feature-ready DataFrames verified for indicator warm-up (e.g., minimum 200 bars for 200 SMA).

### 3.9 Safe Adapters & Mock Provider (`data/realtime/safe_adapters.py`, `data/realtime/mock_provider.py`)
- **`MockRealTimeProvider`**: Fully deterministic streaming simulator with PRNG seeding, multi-stock support (5-stock universe), and fault injection hooks.
- **`KiteRealTimeFeedAdapter`**: Architectural stub for Zerodha Kite Ticker. Implements `RealTimeMarketDataProvider` ABC but strictly fails closed (`MarketDataConnectionError`, `ConnectionState.FAILED`) if live mode is requested. Zero live network calls.

### 3.10 Dashboard Endpoints (`dashboard/server.py`)
- Exposes two isolated read-only REST endpoints:
  - `GET /api/realtime/health`: Returns feed status, connection state, market session state, subscribed symbol count, and throughput metrics.
  - `GET /api/realtime/quotes`: Returns latest cached quotes with age in seconds.

---

## 4. Safety Audit & Boundary Verification

1. **Zero Broker Network Calls**: No network sockets or HTTP requests to external broker servers exist in Step 11.
2. **Fail-Closed Execution**: Downstream execution remains strictly bound to Paper Trading. Attempting live orders via broker adapters triggers `LiveTradingDisabledError`.
3. **No Hardcoded Credentials**: API keys and access tokens are strictly read from environment variables or supplied via constructor; string representations (`__repr__`, `__str__`) scrub credentials.
4. **Binance Legacy System**: Running Binance Testnet bot (`task-1248`) on port 5000 remains completely untouched and isolated.
5. **Deterministic Testing**: Complete 30-test suite runs offline without requiring internet connectivity or paid feeds.
