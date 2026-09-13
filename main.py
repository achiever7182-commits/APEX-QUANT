"""
main.py — Polling-mode bot.

Polls the market every 60 seconds for a new candle, feeds it to the SMA
crossover strategy, checks the risk manager, and places orders through
the REST adapter.

Run with:
    python main.py          # standalone
    python run.py polling   # via unified launcher
"""

from core.strategy import Signal
from core.strategies import get_strategy, list_strategies
from core.risk_manager import RiskManager, RiskConfig
from core.execution import execute_order, fee_tracker
from adapters.binance_adapter import BinanceTestnetAdapter
from config import (
    API_KEY, API_SECRET, SYMBOL, TIMEFRAME, POLL_SECONDS,
    SMA_SHORT, SMA_LONG, DRY_RUN, validate_keys,
)
from utils import readable_time, now_str, log_trade, order_fill_price

import sys
import time

_strategy_name: str = "sma"


def set_strategy(name: str) -> None:
    """Set the strategy used by polling mode."""
    global _strategy_name
    _strategy_name = name.lower()


def run():
    if not validate_keys():
        return

    try:
        strategy = get_strategy(_strategy_name)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    adapter = BinanceTestnetAdapter(API_KEY, API_SECRET, symbol=SYMBOL)

    starting_balance = adapter.fetch_balance("USDT")
    min_notional = adapter.get_min_notional()
    risk = RiskManager(
        starting_balance=starting_balance,
        config=RiskConfig(min_notional=min_notional),
    )
    position_size = 0.0
    entry_price = 0.0
    entry_fee = 0.0

    print(f"Starting bot on {SYMBOL} | strategy: {strategy.name} | balance: {starting_balance:.2f} USDT")

    # Warm up strategy history with recent candles (up to 50 for MACD/Bollinger/SMA)
    for candle in adapter.fetch_candles(timeframe=TIMEFRAME, limit=50):
        strategy.history.append(candle)

    while True:
        try:
            candles = adapter.fetch_candles(timeframe=TIMEFRAME, limit=1)
            latest = candles[-1]
            signal = strategy.update(latest)

            candle_time = readable_time(latest.timestamp)
            print(f"[{candle_time}] price={latest.close:.2f} signal={signal.value}")

            if signal == Signal.BUY and risk.can_open_position():
                capital = risk.position_size()
                if not risk.check_min_notional(capital):
                    time.sleep(POLL_SECONDS)
                    continue
                size = capital / latest.close

                if DRY_RUN:
                    position_size = size
                    entry_price = latest.close
                    entry_fee = size * latest.close * 0.001
                    risk.open_positions += 1
                    risk.mark_trade_executed()
                    log_trade("BUY (DRY)", now_str(), latest.close, size)
                    print(f"  -> [{now_str()}] DRY-RUN BUY placed at {latest.close:.2f} (size={size:.6f})")
                else:
                    fill = execute_order(adapter, "buy", size, latest.close)
                    position_size = fill.filled_qty
                    entry_price = fill.fill_price
                    entry_fee = fill.fee_paid
                    risk.open_positions += 1
                    risk.mark_trade_executed()
                    log_trade("BUY", now_str(), fill.fill_price, fill.filled_qty)
                    print(f"  -> [{now_str()}] BUY order placed: {fill.order_id} at {fill.fill_price:.2f} (fee: {fill.fee_paid:.4f})")

            elif signal == Signal.CLOSE and risk.can_close_position():
                if DRY_RUN:
                    exit_price = latest.close
                    exit_fee = position_size * latest.close * 0.001
                    gross_pnl = (exit_price - entry_price) * position_size
                    net_pnl = gross_pnl - (entry_fee + exit_fee)
                    risk.record_trade_result(net_pnl)
                    risk.open_positions -= 1
                    risk.mark_trade_executed()
                    log_trade("SELL (DRY)", now_str(), exit_price, position_size)
                    print(f"  -> [{now_str()}] DRY-RUN SELL/CLOSE at {exit_price:.2f} | Net P&L: {net_pnl:+.2f} USDT (fees: {entry_fee + exit_fee:.4f})")
                    position_size = 0.0
                    entry_price = 0.0
                    entry_fee = 0.0
                else:
                    fill = execute_order(adapter, "sell", position_size, latest.close)
                    exit_price = fill.fill_price
                    exit_fee = fill.fee_paid
                    gross_pnl = (exit_price - entry_price) * position_size
                    net_pnl = gross_pnl - (entry_fee + exit_fee)
                    risk.record_trade_result(net_pnl)
                    risk.open_positions -= 1
                    risk.mark_trade_executed()
                    log_trade("SELL", now_str(), exit_price, position_size)
                    print(f"  -> [{now_str()}] SELL/CLOSE order: {fill.order_id} at {exit_price:.2f} | Net P&L: {net_pnl:+.2f} USDT (fees: {entry_fee + exit_fee:.4f})")
                    position_size = 0.0
                    entry_price = 0.0
                    entry_fee = 0.0

            else:
                pass

            time.sleep(POLL_SECONDS)

        except KeyboardInterrupt:
            print("Stopped by user.")
            break
        except Exception as e:
            print(f"Error: {e} -- retrying in 10s")
            time.sleep(10)


if __name__ == "__main__":
    run()