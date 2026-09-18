# APEX-QUANT — Frontend V1 Product & Technical Manual

## 1. Product Identity & Purpose

**APEX-QUANT** is an algorithmic quantitative equity research and paper-trading workstation designed for Indian cash equities (NIFTY 50 universe). 

Frontend V1 transitions the user interface from an outdated crypto/Binance bot terminal to a high-density, institutional-grade quantitative equity intelligence platform. It provides complete transparency into model predictions, technical features, multi-factor cross-sectional rankings, integer portfolio optimization, 12-point pre-trade risk controls, double-entry accounting, and continuous reconciliation audits.

---

## 2. Technical Stack & Architecture

- **Framework**: React 18 with TypeScript in strict component architecture.
- **Build Tool**: Vite 6 with TypeScript compiler (`tsc`).
- **Styling**: Tailwind CSS with custom institutional quant color palette (`#080c14` background, `#0f1626` surface, `#00d4ff` cyan accent, `#10b981` bull, `#f43f5e` bear).
- **Icons**: Lucide React.
- **Charts**: Lightweight SVG financial charts (Candlesticks, Volume Sub-charts, Equity Curves with Benchmarks, Horizontal Concentration Gauges).
- **Backend Serving**: Flask (`dashboard/server.py`) serves the compiled production build from `frontend/dist/` with HTML5 client-side routing fallback, alongside REST and WebSocket (`flask_socketio`) endpoints.

```
frontend/
├── dist/                    # Production bundle served by Flask
├── src/
│   ├── api/client.ts        # Centralized typed HTTP API service layer
│   ├── types/index.ts       # Strict TypeScript interfaces matching Python domain models
│   ├── components/          # Reusable workstation UI components
│   │   ├── Header.tsx       # Top bar (Clock, Market Session, Feed, Health, Search, Kill Switch)
│   │   ├── SafetyBanner.tsx # Persistent paper mode & disabled live broker banner
│   │   ├── Navigation.tsx   # Institutional workstation navigation bar (14 tabs)
│   │   ├── MetricCard.tsx   # Compact financial KPI card
│   │   ├── StatusBadge.tsx  # Color-coded state badge (PASS, WARNING, BLOCKED)
│   │   ├── Tooltip.tsx      # Glossary tooltips for quant metrics (Sharpe, IC, etc.)
│   │   ├── KillSwitchModal.tsx # Confirmation modal for paper kill switch
│   │   ├── GlobalSearch.tsx # Quick symbol search modal (Nifty 50)
│   │   └── ErrorState.tsx   # Loading, Empty, and Error state components
│   ├── charts/              # Financial & portfolio charts
│   │   ├── PriceChart.tsx   # Daily OHLCV candlestick & volume chart
│   │   ├── EquityCurveChart.tsx # Strategy equity curve vs benchmarks
│   │   └── AllocationBarChart.tsx # Single-stock and sector exposure bars
│   └── pages/               # 14 Full Synchronized Page Views
│       ├── CommandCenter.tsx
│       ├── Market.tsx
│       ├── Scanner.tsx
│       ├── StockDetail.tsx
│       ├── Portfolio.tsx
│       ├── Orders.tsx
│       ├── Strategies.tsx
│       ├── Backtest.tsx
│       ├── RiskCenter.tsx
│       ├── SystemHealth.tsx
│       ├── Reconciliation.tsx
│       ├── Architecture.tsx
│       ├── PaperTerminal.tsx
│       └── LegacyBinance.tsx
```

---

## 3. Workstation Pages

1. **Command Center (`/`)**: Executive dashboard displaying 8 primary financial KPIs (Total Equity, Available Cash, Invested Capital, Today's P&L, Total P&L, Max Drawdown, Gross Exposure, Open Positions), Top 5 Quant Opportunities, Active Holdings summary, and Subsystem Health indicators.
2. **Market Overview (`/market`)**: Real-time Nifty 50 universe catalog, live bids, asks, spreads, volume, quote freshness, and data source tracking. Explicitly labeled `MOCK REALTIME PROVIDER`.
3. **Stock Scanner (`/scanner`)**: Cross-sectional ranking table with filters for sectors, outlook (Bullish/Neutral/Bearish), risk status (Pass/Warning/Blocked), and minimum quant score. Sortable by rank, score, predicted return, and volatility.
4. **Stock Intelligence (`/stock/:symbol`)**: Deep individual stock intelligence with interactive OHLCV candlestick chart, 66-feature breakdown, 5-day ML prediction, confidence level, and single-stock position limits.
5. **Portfolio (`/portfolio`)**: Double-entry holdings ledger with average cost basis, current prices, market values, unrealized P&L, portfolio weights, and concentration allocation charts with 35% single-stock and 55% sector limit lines.
6. **Orders Ledger (`/orders`)**: Audit ledger of all paper orders and fills with order lifecycle drawer tracing orders through Signal -> Staged -> Risk Check -> Submitted -> Filled -> Accounted -> Reconciled, including rejection diagnostics.
7. **Strategies & ML Lab (`/strategies`)**: Real-world evaluation of the expanding-window RandomForest model (66 features, validation and test MAE, RMSE, Mean IC: +0.0186, IC IR: +0.0342). Transparently displays the research disclaimer regarding historically weak out-of-sample predictability.
8. **Backtest Lab (`/backtest`)**: Historical walk-forward simulation lab across 4 allocation strategies (Constrained, Equal Weight, Quant Score Weighted, Inverse Volatility) and benchmarks (Buy & Hold, Equal Weight Rebalanced, Cash), with quarterly period breakdowns and equity curves.
9. **Risk Center (`/risk`)**: Comprehensive 12-point pre-trade risk monitor with progress utilization gauges for daily loss, drawdown, stock concentration, and sector limits, plus a prominent paper kill-switch control.
10. **System Health (`/system`)**: Subsystem telemetry matrix reporting status, module path, latency, and data freshness across all 17 pipeline components.
11. **Reconciliation (`/reconciliation`)**: Continuous automated tri-party audit comparing local orders, broker orders, execution fills, positions, and cash balances to ensure zero invariant drift.
12. **Architecture Diagram (`/architecture`)**: Interactive topological diagram mapping data flow from Market Data Ingestion through Persistence.
13. **Paper Terminal (`/paper`)**: Manual virtual execution station allowing operators to trigger on-demand rebalance cycles or pause/resume order submission.
14. **Legacy Binance (`/legacy/binance`)**: Quarantined legacy Binance Testnet BTC/USDT momentum bot embedded in an isolated iframe.

---

## 4. State Management & Real-Time Synchronization

- **Server-Driven Truth**: The frontend maintains zero independent or synthetic financial metrics. All numbers are synchronized from backend endpoints.
- **Auto-Refresh Cadence**:
  - Critical prices and quotes: 5s polling.
  - Portfolio, account, and orders: 10s polling.
  - Scanner and model predictions: 15s polling.
- **WebSocket Streaming**: Connects to `SocketIO` at `/socket.io` to receive live tick updates when the market stream or simulation is actively broadcasting.
- **Keyboard Shortcuts**: <kbd>Ctrl+K</kbd> instantly opens the Global Stock Search modal.

---

## 5. Security & Safety Boundaries

- **Zero Credentials in Frontend**: No API keys, secret tokens, or broker secrets exist in client code.
- **Paper Execution Boundary**: Real order placement is architecturally impossible. All orders route through `PaperBroker`.
- **Zero Real Money**: Capital is strictly virtual (₹10,00,000.00 baseline).

---

## 6. Known Limitations

- **Simulated Real-Time Provider**: Streaming quotes are provided by the simulated/mock feed infrastructure built in Step 11. They are not connected to paid live NSE multicast feeds.
- **Empirical Backtest Dataset**: The walk-forward ML backtest evaluated the 5-stock benchmark dataset (RELIANCE, TCS, INFY, HDFCBANK, ICICIBANK) across 11 months due to historical computational constraints.
