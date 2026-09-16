#!/usr/bin/env python3
"""
run.py — Unified launcher for the Trading Bot.

Usage:
    python run.py polling                      # 60s candle polling (SMA crossover)
    python run.py realtime                     # scrolling tick-by-tick dashboard
    python run.py terminal                     # Rich Live full-screen TUI
    python run.py dashboard                    # terminal mode + web dashboard

Flags:
    --strategy <name>    Strategy to use (default: sma for polling, tick for realtime)
    --symbol <pair>      Trading pair (default: BTC/USDT)
    --no-trade           Dry-run: log signals but place no real orders
    --no-browser         Don't auto-open browser (dashboard mode)
    --list-strategies    Show all available strategies and exit

Run `python backtest.py --help` to backtest any strategy before going live.
"""

import argparse
import sys

from config import SYMBOL, validate_keys
from core.strategies import list_strategies


MODES = {
    "polling":   "main",
    "realtime":  "main_realtime",
    "terminal":  "main_terminal_live",
    "dashboard": "main_terminal_live",
}

HELP = f"""\
Trading Bot - Unified Launcher
===============================

Usage: python run.py <mode> [flags]

Modes:
  polling    - Poll Binance every 60s for new candles (SMA crossover strategy)
  realtime   - Tick-by-tick scrolling dashboard via WebSocket
  terminal   - Full-screen Rich Live TUI via WebSocket
  dashboard  - terminal mode + live web dashboard in browser

Flags:
  --strategy <name>   Strategy to use. See --list-strategies for all options.
  --symbol <pair>     Trading pair (default: BTC/USDT)
  --no-trade          Dry-run mode: log signals but place NO real orders
  --no-browser        Don't auto-open browser (dashboard mode only)
  --list-strategies   List all available strategies and exit

Examples:
  python run.py realtime --strategy rsi
  python run.py polling  --strategy macd --symbol ETH/USDT
  python run.py terminal --no-trade
  python run.py dashboard

Backtest any strategy before going live:
  python backtest.py --strategy rsi --candles 1000
  python backtest.py --list

Set API keys before running:
  BINANCE_TESTNET_API_KEY=...
  BINANCE_TESTNET_API_SECRET=...
  (or copy .env.example to .env and fill in your keys)
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Trading Bot Launcher",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    parser.add_argument("mode", nargs="?", default=None)
    parser.add_argument("--strategy", "-s", default=None,
                        help="Strategy name (see --list-strategies)")
    parser.add_argument("--symbol", default=None,
                        help=f"Trading pair (default: {SYMBOL})")
    parser.add_argument("--port", type=int, default=None,
                        help="Web dashboard port (default: 5000)")
    parser.add_argument("--dashboard", "-d", action="store_true",
                        help="Start web dashboard server on localhost:5000")
    parser.add_argument("--no-trade", action="store_true",
                        help="Dry-run: log signals but place no real orders")
    parser.add_argument("--no-browser", action="store_true",
                        help="Don't auto-open browser (dashboard mode only)")
    parser.add_argument("--list-strategies", "-l", action="store_true",
                        help="List all available strategies and exit")
    parser.add_argument("--help", "-h", action="store_true",
                        help="Show this help message and exit")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.list_strategies:
        print("Available strategies:")
        for name in list_strategies():
            print(f"  {name}")
        return

    if args.help or args.mode is None:
        print(HELP)
        sys.exit(0)

    mode = args.mode.lower()
    if mode not in MODES:
        print(f"Unknown mode: '{mode}'")
        print(f"Valid modes: {', '.join(MODES.keys())}")
        sys.exit(1)

    if not validate_keys():
        sys.exit(1)

    # Apply overrides to config at runtime (before importing any entry-point module)
    import config as _cfg
    if args.port:
        _cfg.DASHBOARD_PORT = args.port
    if args.symbol:
        _cfg.SYMBOL = args.symbol
        _cfg.WS_SYMBOL = args.symbol.replace("/", "").lower()
    if args.no_trade:
        _cfg.DRY_RUN = True
        print("[run] DRY-RUN mode enabled — signals will be logged but NO orders placed.")

    print(f"+--- Trading Bot -----------------------------------------+")
    print(f"|  Mode:     {mode:<46}|")
    print(f"|  Symbol:   {_cfg.SYMBOL:<46}|")
    strategy_name = args.strategy or ("sma" if mode == "polling" else "tick")
    print(f"|  Strategy: {strategy_name:<46}|")
    dry = "YES (no orders)" if args.no_trade else "NO"
    print(f"|  Dry-run:  {dry:<46}|")
    print(f"+---------------------------------------------------------+")
    print()

    # Dynamic import — only load deps for the chosen mode
    import importlib
    module = importlib.import_module(MODES[mode])

    if mode == "dashboard" or getattr(args, "dashboard", False):
        # Start web dashboard server, then run the bot
        from dashboard.server import DashboardServer
        server = DashboardServer()
        server.start(open_browser=not args.no_browser)

    # Pass strategy override into module if it supports it
    if args.strategy and hasattr(module, "set_strategy"):
        module.set_strategy(args.strategy)

    try:
        module.run(mode=mode)
    except TypeError:
        module.run()


if __name__ == "__main__":
    main()
