# Multi-Market Trading Bot — Phase 1 (Crypto Testnet)

A modular trading bot designed to eventually trade crypto, forex/indices
(MetaTrader), and stocks — one shared "brain" (strategy + risk manager),
different adapters per market.

## Project Structure

```
Trading-Bot/
├── config.py                  # Shared configuration (API keys, symbol, thresholds)
├── utils.py                   # Shared utilities (timestamps, order helpers, CSV logger)
├── run.py                     # Unified launcher: python run.py <mode>
│
├── main.py                    # Polling mode: 60s candle polling + SMA crossover
├── main_realtime.py           # Realtime mode: scrolling tick-by-tick dashboard
├── main_terminal_live.py      # Terminal mode: Rich Live full-screen TUI
│
├── core/                      # Strategy engine & risk management
│   ├── __init__.py            # Re-exports: Signal, MarketData, RiskManager, ...
│   ├── strategy.py            # Strategy interface + SMA crossover implementation
│   ├── tick_strategy.py       # Tick momentum strategy for real-time modes
│   └── risk_manager.py        # Position sizing, stop-loss, daily loss limits
│
├── adapters/                  # Exchange connectors
│   ├── __init__.py            # Re-exports: BinanceTestnetAdapter, BinanceWebSocketAdapter
│   ├── binance_adapter.py     # REST adapter (orders, balance, candles via ccxt)
│   └── binance_websocket_adapter.py  # WebSocket adapter (live tick stream)
│
├── cpp_trading_bot/           # C++ implementation (standalone, same strategy)
│   ├── config.h               # Shared constants (mirrors config.py)
│   ├── main.cpp               # Full C++ bot (WebSocket + REST + strategy + risk)
│   └── CMakeLists.txt         # Build config (vcpkg dependencies)
│
├── requirements.txt           # Python dependencies
├── vcpkg.json                 # C++ dependencies (vcpkg manifest)
├── .env.example               # Template for API credentials
└── README.md
```

## Quick Start

### 1. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 2. Set up API credentials

Get **free** Binance testnet API keys (no real money) at:
https://testnet.binance.vision/

Option A — Environment variables:
```bash
export BINANCE_TESTNET_API_KEY="your_key_here"
export BINANCE_TESTNET_API_SECRET="your_secret_here"
```

Option B — `.env` file:
```bash
cp .env.example .env
# Edit .env with your keys
```

### 3. Run the bot

Use the unified launcher to pick a mode:

```bash
python run.py polling      # SMA crossover, polls every 60s
python run.py realtime     # Scrolling tick-by-tick dashboard
python run.py terminal     # Full-screen Rich Live TUI
```

Or run any mode directly:
```bash
python main.py                # same as: python run.py polling
python main_realtime.py       # same as: python run.py realtime
python main_terminal_live.py  # same as: python run.py terminal
```

## Trading Modes

| Mode | Strategy | Data Source | Display |
|------|----------|-------------|---------|
| `polling` | SMA Crossover (9/21) | REST candles every 60s | Simple log lines |
| `realtime` | Tick Momentum (0.05%) | WebSocket live ticks | Scrolling colored output |
| `terminal` | Tick Momentum (0.05%) | WebSocket live ticks | Full-screen Rich Live panel |

## C++ Bot

The `cpp_trading_bot/` directory contains a standalone C++ implementation of
the tick momentum strategy with the same Binance testnet REST/WebSocket
integration. It shares configuration defaults via `config.h`.

### Building (requires vcpkg)

```bash
cd cpp_trading_bot
cmake -B build -S . -DCMAKE_TOOLCHAIN_FILE=[vcpkg-root]/scripts/buildsystems/vcpkg.cmake
cmake --build build
```

### Running

```bash
# Set the same env vars as the Python bot
./build/binance_testnet_bot
```

## How It Works

1. **Data** arrives via REST polling (candles) or WebSocket (live ticks)
2. **Strategy** analyzes the data and returns a signal: BUY / SELL / HOLD / CLOSE
3. **Risk Manager** vetoes the signal if position limits, cooldowns, or daily
   loss limits are exceeded
4. **Adapter** places the order on Binance testnet if approved

## Customizing the Strategy

Swap the logic in `core/strategy.py` — write your own class that inherits
from `Strategy` and implements `decide()`. The rest of the system (risk
management, order execution) doesn't need to change.

For tick-based strategies, modify `core/tick_strategy.py` or create a new
class with the same `on_tick(price) -> Signal` interface.

## Configuration

All tunable parameters live in [`config.py`](config.py):

| Parameter | Default | Description |
|-----------|---------|-------------|
| `SYMBOL` | `BTC/USDT` | Trading pair |
| `TIMEFRAME` | `1m` | Candle timeframe (polling mode) |
| `POLL_SECONDS` | `60` | Polling interval |
| `SMA_SHORT` / `SMA_LONG` | `9` / `21` | SMA crossover windows |
| `THRESHOLD_PCT` | `0.05` | Tick momentum threshold (%) |
| `WINDOW_SIZE` | `50` | Tick momentum rolling window |
| `MIN_SECONDS_BETWEEN_TRADES` | `2.0` | Trade cooldown |

## What's Next (Phase 2+)

- **Backtesting**: test strategies against historical data before going live
- **MetaTrader adapter**: forex/indices (MQL5 or Python's `MetaTrader5` package)
- **Stocks adapter**: Alpaca paper trading API
- **Dashboard**: React panel showing live P&L across all connected markets

## ⚠️ Before Going Live With Real Money

- These strategies are teaching examples, not proven money-makers
- Always backtest extensively and run on testnet/paper accounts first
- Never risk more than you can afford to lose — markets are unpredictable
  and past performance doesn't guarantee future results
