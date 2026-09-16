"""
config.py — Single source of truth for every tunable constant.

All three Python entry points (main.py, main_realtime.py, main_terminal_live.py)
import from here instead of hardcoding their own copies.

API keys are read from environment variables. If python-dotenv is installed and
a .env file exists in the project root, it will be loaded automatically.
"""

import os
import sys

# ---------------------------------------------------------------------------
# Optional .env file support
# ---------------------------------------------------------------------------
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed — rely on system env vars

# ---------------------------------------------------------------------------
# API credentials
# ---------------------------------------------------------------------------
API_KEY: str = os.environ.get("BINANCE_TESTNET_API_KEY", "")
API_SECRET: str = os.environ.get("BINANCE_TESTNET_API_SECRET", "")

# ---------------------------------------------------------------------------
# Market / symbol
# ---------------------------------------------------------------------------
SYMBOL: str = "BTC/USDT"
WS_SYMBOL: str = "btcusdt"

# ---------------------------------------------------------------------------
# Polling mode (main.py)
# ---------------------------------------------------------------------------
TIMEFRAME: str = "1m"
POLL_SECONDS: int = 60

# ---------------------------------------------------------------------------
# Realtime / terminal-live modes
# ---------------------------------------------------------------------------
PRINT_INTERVAL_SECONDS: float = 1.0
RECONNECT_CHECK_SECONDS: float = 5.0
LOG_LIMIT: int = 10

# ---------------------------------------------------------------------------
# Strategy parameters
# ---------------------------------------------------------------------------
SMA_SHORT: int = 9
SMA_LONG: int = 21
THRESHOLD_PCT: float = 0.25        # tick momentum threshold (%) — responsive to live price moves
WINDOW_SIZE: int = 30              # tick momentum rolling window (ticks)
TAKE_PROFIT_PCT: float = 0.60      # take profit target (%) — comfortably exceeds 0.20% exchange fees
STOP_LOSS_PCT: float = 0.30        # stop loss target (%)
TRAILING_STOP_PCT: float = 0.20    # trailing profit protection (%)

# ---------------------------------------------------------------------------
# Risk parameters (defaults — RiskConfig also has its own defaults)
# ---------------------------------------------------------------------------
MIN_SECONDS_BETWEEN_TRADES: float = 15.0  # cooldown in seconds — prevents rapid churn while allowing active trades

# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------
EXECUTION_MODE: str = os.environ.get("EXECUTION_MODE", "market")  # "market" for instant fills on testnet, or "limit"
LIMIT_ORDER_TIMEOUT_SECONDS: float = 3.0  # seconds to wait for limit fill before falling back

# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------
STATE_FILE: str = "bot_state.json"

# ---------------------------------------------------------------------------
# Dry-run / paper mode (set by run.py --no-trade flag)
# ---------------------------------------------------------------------------
DRY_RUN: bool = False   # when True, signals are logged but NO orders are placed

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_FILE: str = "trade_log.csv"

# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
DASHBOARD_HOST: str = "127.0.0.1"
DASHBOARD_PORT: int = 5000

# ---------------------------------------------------------------------------
# Backtester
# ---------------------------------------------------------------------------
BACKTEST_STARTING_BALANCE: float = 10_000.0
BACKTEST_FEE_RATE: float = 0.001   # 0.1% Binance taker fee
BACKTEST_LIMIT: int = 1000         # number of candles to fetch for backtesting

# ---------------------------------------------------------------------------
# Machine Learning & Autonomous Trading Prototype
# ---------------------------------------------------------------------------
ML_MODEL_PATH: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "ml_model.joblib")
ML_METADATA_PATH: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "model_metadata.json")
ML_HISTORICAL_DATA_DIR: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "historical")
ML_TIMEFRAME: str = os.environ.get("ML_TIMEFRAME", "5m")
ML_SYMBOL: str = os.environ.get("ML_SYMBOL", "BTC/USDT")
ML_LOOKAHEAD: int = int(os.environ.get("ML_LOOKAHEAD", "3"))
ML_MIN_CONFIDENCE: float = float(os.environ.get("ML_MIN_CONFIDENCE", "0.40"))
BUY_THRESHOLD: float = float(os.environ.get("BUY_THRESHOLD", "0.0015"))      # +0.15%
SELL_THRESHOLD: float = float(os.environ.get("SELL_THRESHOLD", "-0.0015"))  # -0.15%
STOP_LOSS: float = float(os.environ.get("STOP_LOSS", "0.015"))               # 1.5%
TAKE_PROFIT: float = float(os.environ.get("TAKE_PROFIT", "0.025"))           # 2.5%
RISK_PER_TRADE: float = float(os.environ.get("RISK_PER_TRADE", "0.01"))     # 1.0%
SLIPPAGE: float = float(os.environ.get("SLIPPAGE", "0.0005"))               # 0.05%
PAPER_TRADING: bool = os.environ.get("PAPER_TRADING", "true").lower() == "true"
TRADING_MODE: str = os.environ.get("TRADING_MODE", "testnet")



def validate_keys() -> bool:
    """Check that API keys are set. Prints a helpful message and returns False if not."""
    if API_KEY and API_SECRET:
        return True
    print("ERROR: Set BINANCE_TESTNET_API_KEY and BINANCE_TESTNET_API_SECRET first.")
    print("Get free testnet keys at https://testnet.binance.vision/")
    return False
