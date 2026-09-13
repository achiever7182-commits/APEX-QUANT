import argparse
import sys

from config import API_KEY, API_SECRET, SYMBOL, TIMEFRAME, validate_keys
from adapters.binance_adapter import BinanceTestnetAdapter
from adapters.binance_public_data_adapter import BinancePublicDataAdapter
from core.strategies import get_strategy, list_strategies
from core.risk_manager import RiskConfig
from backtester.engine import BacktestEngine
from backtester.metrics import compute_metrics


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare all strategies on Binance historical candle data.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
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
        default=1000,
        help="Number of candles to fetch when using testnet (default: 1000)",
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
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.real_data:
        data_source = f"Binance Public Market Data (REAL, {args.days}d)"
        print(f"Fetching {args.days} days of REAL {args.symbol} {args.timeframe} candles from Binance public market data...")
        adapter = BinancePublicDataAdapter()
        candles = adapter.fetch_historical_candles(
            symbol=args.symbol,
            timeframe=args.timeframe,
            since_days_ago=args.days,
        )
    else:
        if not validate_keys():
            sys.exit(1)
        data_source = f"Binance Testnet ({args.candles} candles)"
        print(f"Fetching {args.candles} {args.symbol} {args.timeframe} candles from Binance testnet...")
        adapter = BinanceTestnetAdapter(API_KEY, API_SECRET, symbol=args.symbol)
        candles = adapter.fetch_candles(timeframe=args.timeframe, limit=args.candles)

    if len(candles) < 30:
        print(f"Not enough candles ({len(candles)}). Need at least 30.")
        sys.exit(1)

    print(f"Got {len(candles)} candles. Data source: {data_source}")
    print("Running all strategies...\n")

    header = f"{'Strategy':<12} {'Trades':>7} {'Return':>10} {'Sharpe':>10} {'MaxDD':>8} {'WinRate':>9} {'PFactor':>9}"
    print(header)
    print("-" * 65)

    results = []
    for name in list_strategies():
        s = get_strategy(name)
        engine = BacktestEngine(
            starting_balance=10000.0,
            risk_config=RiskConfig(min_seconds_between_trades=0.0, max_open_positions=1),
        )
        r = engine.run(s, candles)
        m = compute_metrics(r)
        results.append((name, m))
        pf = "inf" if m.profit_factor == float("inf") else f"{m.profit_factor:.2f}"
        ret_str = f"{m.total_return_pct:+.3f}%"
        print(f"{name:<12} {m.trade_count:>7} {ret_str:>10} {m.sharpe_ratio:>10.3f} {m.max_drawdown_pct:>7.2f}% {m.win_rate_pct:>8.1f}% {pf:>9}")

    print()
    best = max(results, key=lambda x: x[1].total_return_pct)
    print(f"Best on this data: {best[0].upper()} ({best[1].total_return_pct:+.3f}%)")


if __name__ == "__main__":
    main()

