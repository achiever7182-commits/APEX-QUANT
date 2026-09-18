# APEX-QUANT — Frontend Integration Contract & API Specification

## 1. Overview & System Topology

This document specifies the complete contract between the **APEX-QUANT React V1 Workstation** and the **Python Backend Services** (`dashboard/server.py`, `execution/`, `data/`, `risk/`, `ranking/`, `ml/`, `portfolio/`, and `backtesting/`).

The system strictly operates in **PAPER TRADING ONLY** mode (`PaperBroker`).
- **Real Network Broker Calls**: 0
- **Real Money Orders**: 0
- **Live Trading Execution**: Disabled by hard exception boundary (`LiveTradingDisabledError`)

---

## 2. Global Safety & Integrity Rules

1. **Zero Hardcoded Production Metrics**: All displayed equity numbers, cash values, returns, risk utilization, Sharpe, Sortino, CAGR, drawdowns, and orders are retrieved dynamically from the backend API or persistent disk state (`data/paper/`, `data_storage/parquet/adjusted/`, `models/`). Zero hardcoded, fabricated, or fallback metrics are permitted in the client code. Any metric not provided by the API strictly renders as `"N/A"` or `"Not available"`.
2. **Explicit Trading Mode Badges**: Every view displays persistent indicators: `PAPER TRADING`, `SIMULATED REALTIME`, `RESEARCH MODEL`, `HISTORICAL SIMULATION`.
3. **Double-Entry Reconciliation**: Every order and fill is journaled and verified continuously against the accounting ledger via `ReconciliationEngine`.
4. **Isolated Legacy Binance Bot**: The legacy Binance cryptocurrency bot is quarantined under `/legacy/binance` and `/dashboard-compact`, preventing any metric cross-contamination.

---

## 3. Route & Endpoint Contract Matrix

| Frontend Route | Primary View | Backend API Endpoint | HTTP Method | Refresh Cadence | Core Response Schema / Fields |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `/` or `/dashboard` | **Command Center** | `/api/paper/summary`<br>`/api/scanner`<br>`/api/paper/health` | `GET` | 10s auto-refresh | `total_equity`, `cash`, `positions_value`, `daily_pnl`, `realized_pnl`, `unrealized_pnl`, `max_drawdown`, `positions`, `ranked` |
| `/market` | **Market Overview** | `/api/market/universe`<br>`/api/realtime/quotes`<br>`/api/realtime/health` | `GET` | 5s auto-refresh | `universe`: `[{ symbol, company_name, sector, isin, exchange }]`<br>`quotes`: `[{ last_price, bid, ask, volume, age_seconds }]` |
| `/scanner` | **Stock Scanner** | `/api/scanner` | `GET` | 15s auto-refresh | `ranked`: `[{ rank, symbol, price, quant_score, predicted_return, confidence, momentum, volatility, relative_strength, sector, risk_status }]` |
| `/stock/:symbol` | **Stock Intelligence** | `/api/stock/<symbol>` | `GET` | On navigate / 10s | `symbol`, `price`, `day_change`, `quant_score`, `predicted_return_5d`, `confidence`, `features` (RSI, Vol, VolRatio), `risk`, `bars` (90 daily OHLCV) |
| `/portfolio` | **Portfolio Accounting** | `/api/paper/summary`<br>`/api/paper/positions` | `GET` | 10s auto-refresh | `total_equity`, `cash`, `positions`: `[{ symbol, shares, average_cost, current_price, market_value, cost_basis, unrealized_pnl, realized_pnl }]` |
| `/orders` | **Orders Ledger** | `/api/paper/orders`<br>`/api/paper/fills` | `GET` | 10s auto-refresh | `orders`: `[{ order_id, symbol, side, order_type, requested_quantity, filled_quantity, average_fill_price, status, rejection_reason }]` |
| `/strategies` | **Strategies & ML Lab** | `/api/ml/model`<br>`/api/scanner` | `GET` | Static / 15s | `model_name`, `version`, `features`, `metrics` (`val_mae`, `val_rmse`, `val_mean_ic`, `test_mae`, `test_rmse`, `test_mean_ic`, `test_ic_ir`). Missing metrics render as `"N/A"`. |
| `/backtest` | **Backtest Lab** | `/api/backtest/results` | `GET` | Static / On-demand | `period` (`start_date`, `end_date`, `duration_months`, `risk_free_rate`), `strategies` (`constrained`, `equal_weight`, `score_weighted`, `inverse_volatility`), `benchmarks`, `walk_forward_periods`, `equity_curve`. Non-provided benchmark fields render strictly as `"N/A"`. |
| `/risk` | **Risk Center** | `/api/risk/status`<br>`/api/paper/kill_switch` | `GET`<br>`POST` | 5s auto-refresh | `kill_switch`: `{ active, reason }`, `limits`, `utilization`, `checks` (12 checks: kill switch, duplicate, market status, daily loss, drawdown, etc.) |
| `/system` | **System Health** | `/api/paper/health`<br>`/api/realtime/health` | `GET` | 5s auto-refresh | `market_session`, `is_market_open`, `last_reconciliation`, `messages_received`, `dropped_messages`, component status matrix (17 components) |
| `/reconciliation` | **Reconciliation** | `/api/paper/reconciliation` | `GET` | On-demand / 10s | `status`: `"MATCH"` / `"DISCREPANCY"`, `is_clean`, `discrepancies`, `local_orders_count`, `broker_orders_count`, `cash_discrepancy` |
| `/architecture` | **Architecture Diagram** | Interactive UI | N/A | Static | 12-stage interactive topological pipeline diagram mapping Steps 1 through 12. |
| `/paper` | **Paper Terminal** | `/api/paper/summary`<br>`/api/paper/cycle/run` | `GET`<br>`POST` | 5s auto-refresh | Manual rebalance cycle execution trigger, pause/resume orders toggle, positions & recent orders ledger. |
| `/legacy/binance` | **Legacy Binance** | `/dashboard-compact`<br>`/api/state`<br>`/api/trades` | `GET` | Continuous iframe | Isolated BTC/USDT Testnet tick momentum bot iframe with dedicated status telemetry. |

---

## 4. Error Handling Contract

- **Standard HTTP Error Codes**:
  - `400 Bad Request`: Invalid payload parameters.
  - `404 Not Found`: Equity symbol or model artifact not found in storage.
  - `409 Conflict`: Duplicate idempotency key collision or conflicting state.
  - `500 Internal Server Error`: Backend calculation or persistence error. Always returns structured JSON: `{"status": "error", "message": "<sanitized description>"}`.
- **Frontend Fallbacks**:
  - Every view contains an `<ErrorState>` component with a user-friendly retry button.
  - Skeletons and `<LoadingState>` handle transit latency smoothly.
  - Stale quotes (>300 seconds) are visually flagged in amber/red.
  - Outside market hours, the system indicates `CLOSED`, `PRE-MARKET`, `POST-MARKET`, or `WEEKEND`.
