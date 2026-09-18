# APEX QUANT — Step 8: Full Portfolio Backtesting Engine Architecture

## 1. Executive Summary & Overview

The **APEX-QUANT Backtesting Subsystem** (`backtesting/`) provides a realistic, point-in-time safe historical simulation engine for Indian cash equities. It stitches together the entire quantitative research pipeline:

$$\text{Point-in-Time Data} \longrightarrow \text{Step 4 Features} \longrightarrow \text{Step 5 ML Predictions} \longrightarrow \text{Step 6 Ranking} \longrightarrow \text{Step 7 Risk Portfolio} \longrightarrow \text{Simulated Execution} \longrightarrow \text{Accounting Ledger} \longrightarrow \text{Diagnostics}$$

The system answers the fundamental counterfactual question:
> *"If APEX-QUANT had been operating at historical time $T$, using only information available at or before $T$, what portfolio allocation would it have chosen, what trades would have been simulated, what friction costs would have been incurred, and how would portfolio equity have evolved?"*

---

## 2. Complete Pipeline Architecture Diagram

```
                 Historical Market Bars / Storage (Data <= T)
                                      │
                                      ▼
                      Point-in-Time DataFeed (Strictly <= T)
                                      │
                                      ▼
                     BacktestTimeline (Ordered Steps & Cadence)
                                      │
         ┌────────────────────────────┴────────────────────────────┐
         │                                                         │
  On Rebalance Bar t                                     On Non-Rebalance Bar t
         │                                                         │
         ▼                                                         ▼
SignalRunner (Step 6 Ranking)                              Mark-to-Market
  - Scores candidates strictly at t                        - Price updates
  - Emits RankedUniverse                                   - Daily return
         │                                                 - Drawdown tracking
         ▼                                                         │
PortfolioRunner (Step 7 Construction)                              │
  - Solves SLSQP Mean-Variance / Fallbacks                         │
  - Discretizes to Integer Whole Shares                            │
  - Emits PortfolioBuildResult                                     │
         │                                                         │
         ▼                                                         │
ExecutionSimulator                                                 │
  - Sequenced: SELLs first, then BUYs                              │
  - Fills at convention price (next_open/next_close)               │
  - Deducts transaction costs (bps) & slippage (bps)               │
  - Caps by Liquidity Participation Limit                          │
  - Enforces Zero Negative Cash & Integer Shares                   │
         │                                                         │
         ▼                                                         │
PortfolioAccounting                                                │
  - Double-entry position ledger                                   │
  - Realized & Unrealized P&L                                      │
  - Mark-to-market snapshot generation ◄───────────────────────────┘
         │
         ▼
PerformanceAnalyzer & BenchmarkEngine & WalkForwardAnalyzer
  - CAGR, Sharpe, Sortino, Max Drawdown, Calmar
  - Buy-and-Hold & Equal-Weight Benchmarks
  - Sub-period quarterly walk-forward metrics
  - 10-point Invariant Audit
```

---

## 3. Core Subsystem Components

| Module | File | Primary Responsibility |
| :--- | :--- | :--- |
| **Config** | [`backtesting/config.py`](file:///c:/Users/achie/OneDrive/Desktop/Trading-Bot/backtesting/config.py) | Simulation window, cadence, execution convention, fee/slippage basis points. |
| **Models** | [`backtesting/models.py`](file:///c:/Users/achie/OneDrive/Desktop/Trading-Bot/backtesting/models.py) | Strongly typed dataclasses (`SimulatedFill`, `HoldingPosition`, `PortfolioSnapshot`, `BacktestMetrics`, `BacktestResult`). |
| **Timeline** | [`backtesting/timeline.py`](file:///c:/Users/achie/OneDrive/Desktop/Trading-Bot/backtesting/timeline.py) | Ordered simulation dates and rebalance scheduling (`daily`, `weekly`, `biweekly`, `monthly`). |
| **Data Feed** | [`backtesting/data_feed.py`](file:///c:/Users/achie/OneDrive/Desktop/Trading-Bot/backtesting/data_feed.py) | Point-in-time bar slice queries ($\le T$) and execution fill price lookups. |
| **Signal Runner** | [`backtesting/signal_runner.py`](file:///c:/Users/achie/OneDrive/Desktop/Trading-Bot/backtesting/signal_runner.py) | Wraps Step 6 `CrossSectionalRanker` to emit point-in-time `RankedUniverse`. |
| **Portfolio Runner** | [`backtesting/portfolio_runner.py`](file:///c:/Users/achie/OneDrive/Desktop/Trading-Bot/backtesting/portfolio_runner.py) | Wraps Step 7 `PortfolioBuilder` to solve risk-constrained integer allocations. |
| **Execution Simulator** | [`backtesting/execution_simulator.py`](file:///c:/Users/achie/OneDrive/Desktop/Trading-Bot/backtesting/execution_simulator.py) | Simulates fills, slippage, brokerage fees, and liquidity limits without real orders. |
| **Accounting** | [`backtesting/accounting.py`](file:///c:/Users/achie/OneDrive/Desktop/Trading-Bot/backtesting/accounting.py) | Double-entry ledger, cash tracking, average cost basis, realized/unrealized P&L. |
| **Benchmarks** | [`backtesting/benchmarks.py`](file:///c:/Users/achie/OneDrive/Desktop/Trading-Bot/backtesting/benchmarks.py) | Cash, Buy-and-Hold, and Periodic Rebalanced Equal-Weight benchmark series. |
| **Performance** | [`backtesting/performance.py`](file:///c:/Users/achie/OneDrive/Desktop/Trading-Bot/backtesting/performance.py) | Annualized returns, CAGR, Sharpe, Sortino, Calmar, drawdown statistics. |
| **Walk-Forward** | [`backtesting/walk_forward.py`](file:///c:/Users/achie/OneDrive/Desktop/Trading-Bot/backtesting/walk_forward.py) | Chronological sub-period partitioning and expanding-window model training interfaces. |
| **Diagnostics** | [`backtesting/diagnostics.py`](file:///c:/Users/achie/OneDrive/Desktop/Trading-Bot/backtesting/diagnostics.py) | Baseline strategy comparisons, cost attribution, and 10 safety invariant audits. |
| **Engine** | [`backtesting/engine.py`](file:///c:/Users/achie/OneDrive/Desktop/Trading-Bot/backtesting/engine.py) | Master orchestrator coordinating all modules in chronological sequence. |

---

## 4. Point-in-Time Safety & Zero-Lookahead Invariants

Point-in-time safety is the paramount requirement. For any evaluation session $T$:

1. **Allowed Information**: Strictly data where $\text{timestamp} \le T$.
2. **Forbidden Information**: Any prices, volumes, returns, features, corporate actions, or rankings where $\text{timestamp} > T$.
3. **Execution Conventions**:
   - `next_open`: Signals computed from bar $T$'s close are filled at bar $T+1$'s open price. This prevents impossible "look-at-close-and-buy-at-close" anomalies.
   - `next_close`: Signals filled at bar $T+1$'s close.
   - `close_t`: Explicit same-day close assumption (documented research mode).
4. **Leakage Verification**: The subsystem includes dedicated unit tests that deliberately mutate future prices and volume at $T+k$ and mathematically verify that decisions at $T$ remain identical.

---

## 5. Execution, Costs, & Cash Accounting

1. **Sequenced Trade Execution**:
   - SELL orders execute first, crediting cash: $\text{Cash} += \text{Notional} - \text{Fee}$.
   - BUY orders execute second, debiting cash: $\text{Cash} -= \text{Notional} + \text{Fee}$.
2. **Friction Costs**:
   - Transaction fee: $\text{Notional} \times \frac{\text{transaction\_cost\_bps}}{10,000}$ (default: 10 bps).
   - Slippage: Applied adverse to the execution price:
     $$\text{Fill Price}_{\text{BUY}} = P \times (1 + \text{slippage\_rate}), \quad \text{Fill Price}_{\text{SELL}} = P \times (1 - \text{slippage\_rate})$$
3. **Liquidity Participation Cap**:
   - Order sizes cannot exceed $\text{Volume} \times \text{liquidity\_participation\_limit}$ (default: 5% of bar volume).
4. **Whole Share Allocation**:
   - Equities are traded strictly in whole integers: $\text{Shares} \in \mathbb{Z}_{\ge 0}$.
   - Cash buffer prevents negative cash under any rounding or fee scenario.

---

## 6. Realized vs. Expected Returns

The system enforces strict nomenclature separation:
- **Expected Return / Volatility**: Model outputs from Step 5 and Step 7 ($w^T \mu$, $\sqrt{w^T \Sigma w}$). These are NEVER described as actual profit.
- **Realized Return / P&L**: Historical performance achieved by the simulated accounting ledger ($\Delta \text{Equity} / \text{Equity}$).

---

## 7. Limitations & Research Disclaimers

> [!WARNING]
> - **Empirical Universe Limitation**: Empirical testing is conducted on the 5-stock benchmark dataset (`RELIANCE`, `TCS`, `INFY`, `HDFCBANK`, `ICICIBANK`). Full NIFTY 500 scale validation has not occurred.
> - **Zero Profitability Guarantee**: Backtest results represent historical mathematical simulations. Positive historical performance does not guarantee future live profitability.
> - **Cost Model Assumptions**: Transaction costs (10 bps) and slippage (5 bps) are research approximations, not actual statutory contract notes.
> - **No Broker or Live Trading**: No broker APIs or live order placement modules are implemented.
