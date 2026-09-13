"""
backtest.py — Top-level backtesting runner.

Fetches real Binance testnet historical candle data, runs any registered
strategy through the backtesting engine, and prints a full performance report.

Usage:
    python backtest.py                          # default: SMA on BTC/USDT 1m
    python backtest.py --strategy rsi
    python backtest.py --strategy macd --candles 2000
    python backtest.py --strategy bollinger --symbol ETH/USDT
    python backtest.py --list                   # show available strategies
"""

import argparse
import sys

from config import (
    API_KEY, API_SECRET, SYMBOL, TIMEFRAME,
    BACKTEST_STARTING_BALANCE, BACKTEST_FEE_RATE, BACKTEST_LIMIT,
    validate_keys,
)
from core.strategies import get_strategy, list_strategies
from core.risk_manager import RiskConfig
from adapters.binance_adapter import BinanceTestnetAdapter
from adapters.binance_public_data_adapter import BinancePublicDataAdapter
from backtester.engine import BacktestEngine
from backtester.metrics import compute_metrics
from backtester.report import print_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backtest a strategy on Binance historical data.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"Available strategies: {', '.join(list_strategies())}",
    )
    parser.add_argument(
        "--strategy", "-s",
        default="sma",
        help="Strategy name (default: sma)",
    )
    parser.add_argument(
        "--symbol",
        default=SYMBOL,
        help=f"Trading pair (default: {SYMBOL})",
    )
    parser.add_argument(
        "--timeframe", "-t",
        default="1h" if "--real-data" in sys.argv else TIMEFRAME,
        help="Candle timeframe (default: 1h for real-data, 1m for testnet)",
    )

    parser.add_argument(
        "--candles", "-n",
        type=int,
        default=BACKTEST_LIMIT,
        help=f"Number of candles to fetch when using testnet (default: {BACKTEST_LIMIT})",
    )
    parser.add_argument(
        "--real-data",
        action="store_true",
        help="Fetch real Binance historical candles (public, no API keys required)",
    )
    parser.add_argument(
        "--days", "-d",
        type=int,
        default=90,
        help="Number of days of real historical data to fetch when using --real-data (default: 90)",
    )
    parser.add_argument(
        "--walk-forward",
        action="store_true",
        help="Run walk-forward validation across chronological windows to test out-of-sample consistency",
    )
    parser.add_argument(
        "--windows",
        type=int,
        default=4,
        help="Number of chronological windows for walk-forward validation (default: 4)",
    )
    parser.add_argument(
        "--balance",
        type=float,
        default=BACKTEST_STARTING_BALANCE,
        help=f"Starting balance in USDT (default: {BACKTEST_STARTING_BALANCE})",
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="List all available strategies and exit",
    )
    return parser.parse_args()


def run_walk_forward_validation(args, candles) -> None:
    """Run sequential walk-forward window testing to detect overfitting across time."""
    from rich import box
    from rich.console import Console
    from rich.table import Table
    from rich.text import Text
    from datetime import datetime

    console = Console()
    n_windows = max(2, args.windows)
    window_size = len(candles) // n_windows

    console.print()
    console.print(f"[bold cyan]=== WALK-FORWARD VALIDATION ({n_windows} Windows, {args.strategy.upper()}) ===[/bold cyan]")
    console.print(f"Total candles: {len(candles)} | Window size: ~{window_size} candles\n")

    table = Table(box=box.ROUNDED, border_style="bright_blue", show_header=True, header_style="bold cyan")
    table.add_column("Window", style="bold white", justify="center")
    table.add_column("Period", style="bright_black", min_width=22)
    table.add_column("Trades", justify="right")
    table.add_column("Return", justify="right")
    table.add_column("Sharpe", justify="right")
    table.add_column("Max DD", justify="right")
    table.add_column("Win Rate", justify="right")
    table.add_column("Consistency", justify="center")

    returns = []
    for k in range(n_windows):
        start = k * window_size
        end = len(candles) if k == n_windows - 1 else (k + 1) * window_size
        sub_candles = candles[start:end]

        strat = get_strategy(args.strategy)
        eng = BacktestEngine(
            starting_balance=args.balance,
            fee_rate=BACKTEST_FEE_RATE,
            risk_config=RiskConfig(min_seconds_between_trades=0.0, max_open_positions=1),
            symbol=args.symbol,
            timeframe=args.timeframe,
        )
        res = eng.run(strat, sub_candles)
        met = compute_metrics(res)
        returns.append(met.total_return_pct)

        t_start = datetime.fromtimestamp(sub_candles[0].timestamp / 1000).strftime("%Y-%m-%d")
        t_end = datetime.fromtimestamp(sub_candles[-1].timestamp / 1000).strftime("%Y-%m-%d")
        period_str = f"{t_start} -> {t_end}"

        ret_style = "green" if met.total_return_pct >= 0 else "red"
        rating = "PROFIT" if met.total_return_pct > 0 else "LOSS"
        rating_style = "bold green" if met.total_return_pct > 0 else "bold red"

        table.add_row(
            f"W{k + 1}",
            period_str,
            str(met.trade_count),
            Text(f"{met.total_return_pct:+.2f}%", style=ret_style),
            f"{met.sharpe_ratio:.2f}",
            f"{met.max_drawdown_pct:.2f}%",
            f"{met.win_rate_pct:.1f}%",
            Text(rating, style=rating_style),
        )

    console.print(table)

    # Overfitting diagnostic
    profitable_windows = sum(1 for r in returns if r > 0)
    consistency_pct = (profitable_windows / n_windows) * 100
    console.print(f"Profitable Windows: {profitable_windows}/{n_windows} ({consistency_pct:.0f}%)")
    if profitable_windows == n_windows:
        console.print("[bold green]CONSISTENT: Strategy generated positive return across all out-of-sample windows.[/bold green]")
    elif profitable_windows == 0:
        console.print("[bold red]UNDERPERFORMING: Strategy failed to produce positive returns in any walk-forward period.[/bold red]")
    else:
        console.print("[bold yellow]MIXED/REGIME-DEPENDENT: Strategy performance fluctuates across time windows.[/bold yellow]")
    console.print()


def main() -> None:
    args = parse_args()

    if args.list:
        print("Available strategies:")
        for name in list_strategies():
            print(f"  {name}")
        return

    if args.real_data:
        data_source = f"Binance Public Market Data (REAL, {args.days}d)"
        print(f"[backtest] Mode: REAL Binance Market Data ({args.days} days, {args.symbol} {args.timeframe})")
        adapter = BinancePublicDataAdapter()
        candles = adapter.fetch_historical_candles(
            symbol=args.symbol,
            timeframe=args.timeframe,
            since_days_ago=args.days,
        )
    else:
        if not validate_keys():
            sys.exit(1)
        data_source = f"Binance Testnet (TESTNET, {args.candles} candles)"
        print(f"[backtest] Mode: Binance Testnet ({args.candles} x {args.timeframe} candles for {args.symbol})")
        adapter = BinanceTestnetAdapter(API_KEY, API_SECRET, symbol=args.symbol)
        candles = adapter.fetch_candles(timeframe=args.timeframe, limit=args.candles)

    if len(candles) < 30:
        print(f"[backtest] Not enough candles ({len(candles)}). Try a higher --candles or --days value.")
        sys.exit(1)

    if args.walk_forward:
        run_walk_forward_validation(args, candles)

    print(f"[backtest] Running full {args.strategy.upper()} strategy on {len(candles)} candles...")
    strategy = get_strategy(args.strategy)

    engine = BacktestEngine(
        starting_balance=args.balance,
        fee_rate=BACKTEST_FEE_RATE,
        risk_config=RiskConfig(min_seconds_between_trades=0.0, max_open_positions=1),
        symbol=args.symbol,
        timeframe=args.timeframe,
    )
    result = engine.run(strategy, candles)
    metrics = compute_metrics(result)
    print_report(result, metrics, data_source=data_source)



if __name__ == "__main__":
    main()

