# APEX-QUANT — Step 12: End-to-End Paper Trading Integration Architecture

## 1. Overview & System Purpose

Step 12 completes the unified, production-oriented quantitative trading lifecycle in APEX-QUANT, integrating all previous milestones into a cohesive, deterministic paper trading runtime engine:

$$\text{Realtime Data} \to \text{Validation/Normalization} \to \text{Bar Aggregation} \to \text{Historical Handoff} \to \text{Feature Engine} \to \text{Walk-Forward ML} \to \text{Cross-Sectional Ranking} \to \text{Portfolio Construction} \to \text{Pre-Trade Risk Engine} \to \text{Order Sequencing (SELLs-then-BUYs)} \to \text{Paper Broker} \to \text{Accounting Ledger} \to \text{Reconciliation Engine} \to \text{State Persistence} \to \text{Telemetry/Dashboard}$$

### Safety Boundary Guarantee
- **Zero Real Orders**: No live broker endpoints, accounts, or real funds are touched or connectable.
- **Fail-Closed Locking**: The system is permanently locked to paper execution mode (`PAPER-ONLY`). Any attempt to submit an order with `ExecutionMode.LIVE` or connect to live broker order routing raises `LiveTradingDisabledError`.
- **Legacy Binance Isolation**: The existing Binance Testnet bot (`run.py realtime`) is fully separated and remains completely unaffected.

---

## 2. Integrated Architectural Pipeline

### Pipeline Flow

```
+----------------------------------------------------------------------------------------------------+
|                                    1. REALTIME MARKET DATA FEED                                    |
|   - LatestQuoteCache / MarketDataSafetyAdapter / RealtimeDataValidator / FeedHealthMonitor         |
|   - Rejects: non-positive prices, stale quotes (>300s), clock skew, crossed bid/ask               |
+----------------------------------------------------------------------------------------------------+
                                                  │
                                                  ▼
+----------------------------------------------------------------------------------------------------+
|                                      2. MARKET CALENDAR & SESSION                                  |
|   - NSEMarketCalendar / MarketSessionState                                                         |
|   - Gates execution outside REGULAR_HOURS (09:15-15:30 IST) or on weekends/holidays                |
+----------------------------------------------------------------------------------------------------+
                                                  │
                                                  ▼
+----------------------------------------------------------------------------------------------------+
|                                  3. DATA HANDOFF & FEATURE ENGINEERING                             |
|   - HistoricalRealtimeHandoff + FeatureEngine                                                      |
|   - Pre-pends historical daily/minute bars to streaming ticks; ensures minimum warm-up (60+ bars)  |
+----------------------------------------------------------------------------------------------------+
                                                  │
                                                  ▼
+----------------------------------------------------------------------------------------------------+
|                                  4. POINT-IN-TIME WALK-FORWARD ML                                  |
|   - WalkForwardMLTrainer (Ridge / Gradient Boosting / Random Forest)                               |
|   - Strictly trained on observations available <= T; zero look-ahead bias                         |
+----------------------------------------------------------------------------------------------------+
                                                  │
                                                  ▼
+----------------------------------------------------------------------------------------------------+
|                                    5. CROSS-SECTIONAL RANKING                                      |
|   - SignalRunner + CrossSectionalRanker + UniverseManager                                          |
|   - Percentile/Z-score normalization, risk adjustment, top-K selection, PIT membership gating      |
+----------------------------------------------------------------------------------------------------+
                                                  │
                                                  ▼
+----------------------------------------------------------------------------------------------------+
|                                   6. PORTFOLIO CONSTRUCTION                                        |
|   - PortfolioRunner + PortfolioBuilder                                                             |
|   - Constraints: max positions, single-stock (35%), sector (50%), gross exposure (95%), 5% cash    |
|   - Integer share rounding with transaction fee modeling                                           |
+----------------------------------------------------------------------------------------------------+
                                                  │
                                                  ▼
+----------------------------------------------------------------------------------------------------+
|                                    7. PRE-TRADE RISK ENGINE (12 CHECKS)                            |
|   - PaperRiskManager (Kill Switch, Idempotency, Market Open, Price, Notional, Loss, Drawdown, ...) |
|   - Bounded numerical tolerance (50 bps) for execution fee drag & tick rounding                    |
+----------------------------------------------------------------------------------------------------+
                                                  │
                                                  ▼
+----------------------------------------------------------------------------------------------------+
|                                   8. ORDER MANAGER & SEQUENCING                                    |
|   - OrderManager                                                                                   |
|   - Order sequencing: SELLs executed FIRST to free cash, BUYs executed SECOND                      |
|   - Generates deterministic idempotency keys: ORD-{cycle_id}-{symbol}-{side}                       |
+----------------------------------------------------------------------------------------------------+
                                                  │
                                                  ▼
+----------------------------------------------------------------------------------------------------+
|                                      9. PAPER BROKER & EXECUTION                                   |
|   - PaperBroker                                                                                    |
|   - Realistic market simulation: slippage (5 bps) + transaction costs (10 bps), partial fill support |
+----------------------------------------------------------------------------------------------------+
                                                  │
                                                  ▼
+----------------------------------------------------------------------------------------------------+
|                                 10. DOUBLE-ENTRY ACCOUNTING LEDGER                                 |
|   - PaperAccounting                                                                                |
|   - Invariant: Cash + Sum(Positions Market Value) == Total Equity                                  |
+----------------------------------------------------------------------------------------------------+
                                                  │
                                                  ▼
+----------------------------------------------------------------------------------------------------+
|                                  11. POST-TRADE RECONCILIATION ENGINE                              |
|   - ReconciliationEngine                                                                           |
|   - Audits actual positions vs target positions, double-entry balance identity, fill cash flow     |
+----------------------------------------------------------------------------------------------------+
                                                  │
                                                  ▼
+----------------------------------------------------------------------------------------------------+
|                                 12. ATOMIC STATE PERSISTENCE & AUDIT                               |
|   - PaperStatePersistence                                                                          |
|   - Atomic writes to data/paper/{account.json, positions.json, orders.json, fills.json, events}   |
+----------------------------------------------------------------------------------------------------+
                                                  │
                                                  ▼
+----------------------------------------------------------------------------------------------------+
|                                      13. TELEMETRY & DASHBOARD API                                 |
|   - /api/paper/cycle, /api/paper/signals, /api/paper/portfolio, /api/paper/reconciliation, /health |
+----------------------------------------------------------------------------------------------------+
```

---

## 3. Key Components & Implementation Details

### 3.1 Orchestrator Core (`execution/paper/orchestrator.py`)
- **Class**: `PaperTradingOrchestrator`
- **Method**: `run_cycle(...)`
- **Cycle Lifecycle State**: `CycleState` (`INIT`, `MARKET_CLOSED_SKIPPED`, `DATA_INGESTED`, `SIGNALS_GENERATED`, `PORTFOLIO_CONSTRUCTED`, `RISK_EVALUATED`, `ORDERS_EXECUTED`, `RECONCILED`, `COMPLETED`, `ALREADY_PROCESSED`, `DATA_FAILED`, `MODEL_FAILED`, `PORTFOLIO_FAILED`, `RECONCILIATION_FAILED`).
- **Idempotency Guard**: Rejects duplicate runs of the exact same cycle identifier (`NSE-YYYYMMDD_HHMMSS-V1`).
- **Per-Stock Fault Isolation**: Unhealthy, corrupt, or stale quotes are logged and excluded individually; healthy universe candidates proceed unimpeded.
- **Fail-Closed Architecture**: Any catastrophic model or solver failure immediately halts downstream order generation without corrupting the portfolio.

### 3.2 Order Sequencing & Cash Management
- Target portfolio deltas are decomposed into SELL and BUY orders.
- SELL orders execute **first**, liberating cash into the paper account ledger before BUY orders consume cash.
- Each order receives a cryptographic idempotency key: `ORD-{cycle_id}-{symbol}-{side}`.

### 3.3 Reconciliation & Discrepancy Auditor (`execution/reconciliation.py`)
- Audits five independent criteria:
  1. `BALANCE_IDENTITY`: Cash + Positions Value == Total Equity.
  2. `CASH_FILL_AUDIT`: Initial Capital + Net Fills Flow == Current Cash.
  3. `DUPLICATE_FILL`: Detects duplicated fill identifiers.
  4. `TARGET_SHARES_MISMATCH`: Target Portfolio Shares vs Actual Broker Shares.
  5. `EXPECTED_CASH_MISMATCH`: Target Cash vs Actual Cash (with 5.0 INR execution/rounding tolerance).

### 3.4 Telemetry & Dashboard Integration (`dashboard/server.py`)
New REST API endpoints added:
- `GET /api/paper/cycle`: Latest cycle execution status, timings, and summary.
- `GET /api/paper/signals`: Point-in-time ML signals and predicted returns for active candidates.
- `GET /api/paper/portfolio`: Current portfolio weights, holdings, cash reserve, and target decisions.
- `GET /api/paper/reconciliation`: Audit report with status, balance identities, and discrepancies.
- `GET /api/paper/health`: Overall health check, kill switch status, and uptime.
