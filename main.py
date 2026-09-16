"""
main.py — Autonomous ML Trading Prototype & Multi-Mode CLI.

Modes:
  1. backtest:  Test MLStrategy against unseen historical data with slippage & fee simulation.
  2. replay:    Step-by-step playback of historical candles with AI decision boxes & dashboard updates.
  3. testnet:   Live paper trading on Binance Testnet (testnet funds only) driven by ML predictions.
  4. polling:   Legacy polling loop using simple moving averages.

Usage:
  python main.py --mode backtest
  python main.py --mode replay --candles 60 --delay 0.2
  python main.py --mode testnet --timeframe 5m
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Any

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

import config
from adapters.binance_adapter import BinanceTestnetAdapter
from backtester.engine import BacktestEngine
from backtester.metrics import compute_metrics
from core.execution import execute_order
from core.risk_manager import RiskManager, RiskConfig
from core.strategies import get_strategy
from core.strategies.ml_strategy import MLStrategy
from core.strategy import MarketData, Signal
from dashboard.server import DashboardServer, emit_state
from ml.data_loader import load_historical_data
from ml.model import MLModel
from ml.predict import format_prediction_box, predict_candle
from state.store import StateStore
from utils import log_trade, now_str, readable_time

console = Console()
_strategy_name: str = "sma"


def set_strategy(name: str) -> None:
    """Set the strategy used by legacy polling mode."""
    global _strategy_name
    _strategy_name = name.lower()


# ===========================================================================
# 1. BACKTEST MODE
# ===========================================================================

def run_backtest(args: argparse.Namespace) -> None:
    console.print()
    banner = Panel.fit(
        "[bold cyan]AUTONOMOUS ML TRADING PROTOTYPE — HISTORICAL BACKTEST[/bold cyan]\n"
        f"[dim]Symbol: {args.symbol} | Timeframe: {args.timeframe} | Slippage: {config.SLIPPAGE * 100:.2f}% | Fee: 0.10%[/dim]",
        border_style="cyan",
    )
    console.print(banner)
    console.print()

    # Verify model exists
    if not os.path.exists(args.model_path):
        console.print(f"[yellow]Warning: Model not found at {args.model_path}. Training now...[/yellow]")
        from ml.train import train_pipeline
        train_pipeline(
            symbol=args.symbol,
            timeframe=args.timeframe,
            days=args.days,
            min_confidence=args.confidence,
            output_path=args.model_path,
        )

    # 1. Load Data
    console.print(f"Loading {args.days} days of historical candles for {args.symbol} ({args.timeframe})...")
    candles = load_historical_data(symbol=args.symbol, timeframe=args.timeframe, days=args.days)
    console.print(f"[green][OK][/green] Loaded {len(candles):,} candles.\n")

    # 2. Run Strategy Backtest
    strategy = MLStrategy(
        model_path=args.model_path,
        min_confidence=args.confidence,
        stop_loss=config.STOP_LOSS,
        take_profit=config.TAKE_PROFIT,
    )
    engine = BacktestEngine(
        starting_balance=10_000.0,
        fee_rate=0.001,
        slippage_pct=config.SLIPPAGE,
        symbol=args.symbol,
        timeframe=args.timeframe,
    )
    result = engine.run(strategy, candles)
    m = compute_metrics(result)

    # 3. Display Results
    t = Table(box=box.ROUNDED, border_style="green", title="ML Strategy Simulated Backtest Performance")
    t.add_column("Metric", style="bright_black", min_width=25)
    t.add_column("Value", justify="right", min_width=20)

    t.add_row("Starting Capital", f"${result.starting_balance:,.2f}")
    t.add_row("Ending Capital", f"${result.final_balance:,.2f}")
    t.add_row("Net Profit / Loss", f"${m.total_pnl:+,.2f}")
    t.add_row("Total Return", f"{m.total_return_pct:+.2f}%")
    t.add_row("Total Trades", str(m.trade_count))
    t.add_row("Win Rate", f"{m.win_rate_pct:.2f}% ({m.win_count}W / {m.loss_count}L)")
    t.add_row("Profit Factor", f"{m.profit_factor:.4f}" if m.profit_factor != float("inf") else "Inf")
    t.add_row("Max Drawdown", f"{m.max_drawdown_pct:.2f}%")
    t.add_row("Sharpe Ratio", f"{m.sharpe_ratio:.4f}")
    t.add_row("Total Fees Paid", f"${m.total_fees:,.2f}")

    console.print(t)
    console.print()

    # Print trade breakdown
    if result.trades:
        t_trades = Table(box=box.SIMPLE, title="Executed Trades (Sample of last 10)")
        t_trades.add_column("Entry Time")
        t_trades.add_column("Exit Time")
        t_trades.add_column("Entry Price", justify="right")
        t_trades.add_column("Exit Price", justify="right")
        t_trades.add_column("Net P&L", justify="right")
        t_trades.add_column("Reason")

        for tr in result.trades[-10:]:
            pnl_style = "green" if tr.pnl > 0 else "red"
            t_trades.add_row(
                readable_time(tr.entry_time),
                readable_time(tr.exit_time),
                f"${tr.entry_price:,.2f}",
                f"${tr.exit_price:,.2f}",
                f"[{pnl_style}]${tr.pnl:+,.2f}[/{pnl_style}]",
                getattr(tr, "exit_reason", "signal"),
            )
        console.print(t_trades)
        console.print()


# ===========================================================================
# 2. REPLAY MODE
# ===========================================================================

def run_replay(args: argparse.Namespace) -> None:
    console.print()
    banner = Panel.fit(
        "[bold magenta]AUTONOMOUS ML TRADING PROTOTYPE — AUTONOMOUS REPLAY MODE[/bold magenta]\n"
        f"[dim]Replaying historical candles sequentially with real-time AI decision outputs & dashboard stream[/dim]",
        border_style="magenta",
    )
    console.print(banner)
    console.print()

    if not os.path.exists(args.model_path):
        console.print(f"[yellow]Warning: Model not found at {args.model_path}. Training first...[/yellow]")
        from ml.train import train_pipeline
        train_pipeline(symbol=args.symbol, timeframe=args.timeframe, days=args.days, min_confidence=args.confidence, output_path=args.model_path)

    # Start dashboard
    dashboard_server = None
    if not args.no_dashboard:
        try:
            dashboard_server = DashboardServer()
            dashboard_server.start(open_browser=not args.no_browser)
            time.sleep(1.0)
        except Exception as err:
            console.print(f"[yellow]Dashboard warning: {err}[/yellow]")

    # Load candles
    all_candles = load_historical_data(symbol=args.symbol, timeframe=args.timeframe, days=args.days)
    count = args.candles if args.candles > 0 else len(all_candles)
    # Take warmup + replay window
    warmup_count = 35
    total_needed = warmup_count + count
    slice_candles = all_candles[-total_needed:] if len(all_candles) >= total_needed else all_candles

    strategy = MLStrategy(
        model_path=args.model_path,
        min_confidence=args.confidence,
        stop_loss=config.STOP_LOSS,
        take_profit=config.TAKE_PROFIT,
    )
    risk = RiskManager(starting_balance=10_000.0, config=RiskConfig(min_notional=10.0, min_seconds_between_trades=0.0))

    # Pre-populate history with warmup candles
    warmup_slice = slice_candles[:warmup_count]
    replay_slice = slice_candles[warmup_count:]
    for c in warmup_slice:
        strategy.history.append(c)

    console.print(f"[green][OK][/green] Initialized with {len(warmup_slice)} warmup candles. Replaying {len(replay_slice)} candles at {args.delay}s per candle...\n")

    balance = 10_000.0
    position_open = False
    position_size = 0.0
    entry_price = 0.0
    entry_fee = 0.0
    realized_pnl = 0.0
    trade_count = 0
    win_count = 0
    loss_count = 0
    total_fees = 0.0
    actions_list: list[dict[str, Any]] = []

    for i, candle in enumerate(replay_slice):
        signal = strategy.update(candle)
        price = candle.close
        pred = getattr(strategy, "last_prediction", None)

        # Print AI Terminal Box
        if pred:
            print(format_prediction_box(pred, symbol=args.symbol))
        else:
            time_str = readable_time(candle.timestamp)
            print(f"[{time_str}] Price: ${price:,.2f} | Signal: {signal.value}")

        last_action = None

        # Intraday SL / TP
        if position_open:
            sl_hit = False
            tp_hit = False
            exit_p = price

            if config.STOP_LOSS and candle.low <= entry_price * (1.0 - config.STOP_LOSS):
                sl_hit = True
                exit_p = entry_price * (1.0 - config.STOP_LOSS) * (1.0 - config.SLIPPAGE)
            elif config.TAKE_PROFIT and candle.high >= entry_price * (1.0 + config.TAKE_PROFIT):
                tp_hit = True
                exit_p = entry_price * (1.0 + config.TAKE_PROFIT) * (1.0 - config.SLIPPAGE)

            if sl_hit or tp_hit:
                exit_fee = exit_p * position_size * 0.001
                net_pnl = (exit_p - entry_price) * position_size - exit_fee
                balance += net_pnl
                realized_pnl += net_pnl
                total_fees += exit_fee
                trade_count += 1
                if net_pnl > 0:
                    win_count += 1
                else:
                    loss_count += 1
                risk.record_trade_result(net_pnl)
                risk.open_positions = max(0, risk.open_positions - 1)
                reason_tag = "STOP_LOSS" if sl_hit else "TAKE_PROFIT"
                log_trade(f"SELL ({reason_tag})", readable_time(candle.timestamp), exit_p, position_size, pnl=net_pnl, reason=reason_tag)
                last_action = {
                    "timestamp": readable_time(candle.timestamp),
                    "action": "SELL",
                    "price": round(exit_p, 2),
                    "pnl": round(net_pnl, 2),
                    "order_id": f"sl_tp_{i}",
                }
                actions_list.insert(0, last_action)
                position_open = False
                strategy._position_open = False
                print(f"  -> [{reason_tag}] Executed auto-close at ${exit_p:,.2f} | P&L: ${net_pnl:+,.2f}")

        # BUY execution
        if signal == Signal.BUY and not position_open and risk.can_open_position():
            eff_price = price * (1.0 + config.SLIPPAGE)
            capital = risk.position_size()
            fee = capital * 0.001
            position_size = (capital - fee) / eff_price
            entry_price = eff_price
            entry_fee = fee
            total_fees += fee
            balance -= fee
            position_open = True
            risk.open_positions += 1
            risk.mark_trade_executed()
            trade_count += 1
            log_trade("BUY", readable_time(candle.timestamp), eff_price, position_size, confidence=pred.confidence if pred else 0.0, reason=pred.reason if pred else "")
            last_action = {
                "timestamp": readable_time(candle.timestamp),
                "action": "BUY",
                "price": round(eff_price, 2),
                "order_id": f"buy_{i}",
            }
            actions_list.insert(0, last_action)
            print(f"  -> [BUY ORDER] Filled {position_size:.6f} BTC at ${eff_price:,.2f} (Fee: ${fee:.4f})")

        # CLOSE execution
        elif signal == Signal.CLOSE and position_open:
            eff_price = price * (1.0 - config.SLIPPAGE)
            exit_fee = eff_price * position_size * 0.001
            net_pnl = (eff_price - entry_price) * position_size - exit_fee
            balance += net_pnl
            realized_pnl += net_pnl
            total_fees += exit_fee
            if net_pnl > 0:
                win_count += 1
            else:
                loss_count += 1
            risk.record_trade_result(net_pnl)
            risk.open_positions = max(0, risk.open_positions - 1)
            risk.mark_trade_executed()
            log_trade("SELL", readable_time(candle.timestamp), eff_price, position_size, pnl=net_pnl, confidence=pred.confidence if pred else 0.0, reason=pred.reason if pred else "")
            last_action = {
                "timestamp": readable_time(candle.timestamp),
                "action": "SELL",
                "price": round(eff_price, 2),
                "pnl": round(net_pnl, 2),
                "order_id": f"sell_{i}",
            }
            actions_list.insert(0, last_action)
            position_open = False
            print(f"  -> [SELL ORDER] Closed at ${eff_price:,.2f} | Net P&L: ${net_pnl:+,.2f} (Fee: ${exit_fee:.4f})")

        # Emit state to dashboard
        unrealized = (price - entry_price) * position_size if position_open else 0.0
        state = {
            "symbol": args.symbol,
            "timeframe": args.timeframe,
            "price": price,
            "signal": pred.signal if pred else signal.value,
            "confidence": pred.confidence if pred else 0.0,
            "probabilities": {
                "BUY": pred.buy_probability if pred else 0.0,
                "HOLD": pred.hold_probability if pred else 1.0,
                "SELL": pred.sell_probability if pred else 0.0,
            },
            "reason": pred.reason if pred else "",
            "balance": balance,
            "starting_balance": 10_000.0,
            "realized_pnl": realized_pnl,
            "unrealized_pnl": unrealized,
            "position_open": position_open,
            "entry_price": entry_price,
            "position_size": position_size,
            "trade_count": trade_count,
            "win_count": win_count,
            "loss_count": loss_count,
            "total_fees_paid": total_fees,
            "last_action": last_action,
            "actions": list(actions_list[:20]),
        }
        emit_state(state)

        if args.delay > 0:
            time.sleep(args.delay)

    console.print()
    console.print("[bold green][OK] Replay session completed successfully.[/bold green]")
    console.print(f"Realized P&L: ${realized_pnl:+,.2f} | Win Rate: {(win_count / max(win_count + loss_count, 1) * 100):.1f}% ({win_count}W/{loss_count}L) | Trades: {trade_count}")
    console.print()

    if not args.no_dashboard and dashboard_server:
        console.print("[bold cyan]Dashboard server active at http://127.0.0.1:5000. Press Ctrl+C to exit.[/bold cyan]")
        try:
            while True:
                time.sleep(1.0)
        except KeyboardInterrupt:
            console.print("\nExiting dashboard.")


# ===========================================================================
# 3. TESTNET MODE (LIVE BINANCE TESTNET PAPER TRADING)
# ===========================================================================

def run_testnet(args: argparse.Namespace) -> None:
    console.print()
    banner = Panel.fit(
        "[bold yellow]BINANCE TESTNET — LIVE AUTONOMOUS ML EXECUTION[/bold yellow]\n"
        "[dim]Paper trading with fake funds on Binance Testnet (https://testnet.binance.vision)[/dim]",
        border_style="yellow",
    )
    console.print(banner)
    console.print()

    if not config.validate_keys():
        console.print("[bold red]Error:[/bold red] Missing or invalid Binance API keys. Please set BINANCE_API_KEY and BINANCE_API_SECRET in .env.")
        sys.exit(1)

    if not os.path.exists(args.model_path):
        console.print(f"[yellow]Warning: Model not found at {args.model_path}. Training first...[/yellow]")
        from ml.train import train_pipeline
        train_pipeline(symbol=args.symbol, timeframe=args.timeframe, days=args.days, min_confidence=args.confidence, output_path=args.model_path)

    # Start dashboard
    if not args.no_dashboard:
        try:
            d_server = DashboardServer()
            d_server.start(open_browser=not args.no_browser)
            time.sleep(1.0)
        except Exception as err:
            console.print(f"[yellow]Dashboard warning: {err}[/yellow]")

    adapter = BinanceTestnetAdapter(config.API_KEY, config.API_SECRET, symbol=args.symbol)
    balance = adapter.fetch_balance("USDT")
    min_notional = adapter.get_min_notional()

    store = StateStore()
    persisted = store.load()
    if not config.DRY_RUN:
        persisted = store.reconcile_with_exchange(persisted, adapter, base_asset="BTC")

    risk = RiskManager(
        starting_balance=balance,
        config=RiskConfig(
            min_notional=min_notional,
            min_seconds_between_trades=getattr(config, "MIN_SECONDS_BETWEEN_TRADES", 15.0),
        ),
    )

    strat_name = (getattr(args, "strategy", None) or _strategy_name or "ml").lower()

    if strat_name == "ml":
        strategy = MLStrategy(
            model_path=args.model_path,
            min_confidence=args.confidence,
            stop_loss=config.STOP_LOSS,
            take_profit=config.TAKE_PROFIT,
        )
    elif strat_name in ("tick", "momentum", "tick_momentum"):
        from core.tick_strategy import TickMomentumStrategy
        strategy = TickMomentumStrategy(
            threshold_pct=getattr(config, "THRESHOLD_PCT", 0.08),
            window_size=getattr(config, "WINDOW_SIZE", 30),
            take_profit_pct=getattr(config, "TAKE_PROFIT_PCT", 0.08),
            stop_loss_pct=getattr(config, "STOP_LOSS_PCT", 0.08),
            trailing_stop_pct=getattr(config, "TRAILING_STOP_PCT", 0.04),
        )
    else:
        try:
            strategy = get_strategy(strat_name)
        except Exception:
            console.print(f"[yellow]Unknown strategy '{strat_name}', using ML[/yellow]")
            strategy = MLStrategy(
                model_path=args.model_path,
                min_confidence=args.confidence,
                stop_loss=config.STOP_LOSS,
                take_profit=config.TAKE_PROFIT,
            )

    console.print(f"[green][OK][/green] Connected to Binance Testnet.")
    console.print(f"Starting balance: ${balance:,.2f} USDT | Min Notional: ${min_notional:.2f} | Strategy: {strat_name.upper()}")

    # Warm up with recent 50 candles
    console.print(f"Fetching 50 historical candles for warmup ({strat_name.upper()})...")
    history_candles = adapter.fetch_candles(timeframe=args.timeframe, limit=50)
    for c in history_candles:
        if hasattr(strategy, "history"):
            strategy.history.append(c)
        elif hasattr(strategy, "window"):
            strategy.window.append(c.close)

    console.print("[green][OK][/green] Strategy warm-up complete. Entering live execution loop...\n")

    realized_pnl = float(persisted.get("realized_pnl", 0.0))
    trade_count = int(persisted.get("trade_count", 0))
    win_count = int(persisted.get("win_count", 0))
    loss_count = int(persisted.get("loss_count", 0))
    total_fees = float(persisted.get("total_fees_paid", 0.0))

    position_open = False
    position_size = 0.0
    entry_price = 0.0
    entry_fee = 0.0

    actions_list: list[dict[str, Any]] = []
    if persisted.get("trade_history"):
        for th in persisted["trade_history"]:
            if "action" in th:
                actions_list.insert(0, th)
            else:
                if th.get("exit_time") and th.get("exit_price"):
                    actions_list.insert(0, {
                        "timestamp": th.get("exit_time"),
                        "action": "SELL",
                        "price": float(th.get("exit_price", 0.0)),
                        "pnl": float(th.get("pnl", 0.0)),
                        "order_id": str(th.get("exit_order_id") or ""),
                    })
                if th.get("entry_time") and th.get("entry_price"):
                    actions_list.insert(0, {
                        "timestamp": th.get("entry_time"),
                        "action": "BUY",
                        "price": float(th.get("entry_price", 0.0)),
                        "pnl": None,
                        "order_id": str(th.get("entry_order_id") or ""),
                    })

    if persisted.get("open_position"):
        open_pos = persisted["open_position"]
        position_open = True
        position_size = float(open_pos.get("size", 0.0))
        entry_price = float(open_pos.get("entry_price", 0.0))
        entry_fee = float(open_pos.get("entry_fee", 0.0))
        risk.open_positions = 1
        if hasattr(strategy, "set_open_position"):
            strategy.set_open_position(entry_price=entry_price, entry_time=open_pos.get("entry_time"))
        elif hasattr(strategy, "_position_open"):
            strategy._position_open = True

    poll_interval = getattr(args, "interval", None) or 3

    while True:
        try:
            candles = adapter.fetch_candles(timeframe=args.timeframe, limit=2)
            if not candles:
                time.sleep(poll_interval)
                continue

            latest = candles[-1]
            price = latest.close

            if hasattr(strategy, "on_tick"):
                signal = strategy.on_tick(price)
            else:
                signal = strategy.update(latest)

            pred = getattr(strategy, "last_prediction", None)

            # Build clean AI signals and probabilities for display & dashboard
            if pred:
                sig_str = pred.signal
                conf_val = pred.confidence
                probs = {
                    "BUY": pred.buy_probability,
                    "HOLD": pred.hold_probability,
                    "SELL": pred.sell_probability,
                }
                reason_str = pred.reason
                print(format_prediction_box(pred, symbol=args.symbol), flush=True)
            else:
                sig_str = "SELL" if signal in (Signal.CLOSE, Signal.SELL) else signal.value
                conf_val = 0.85 if signal in (Signal.BUY, Signal.CLOSE, Signal.SELL) else 0.50
                p_buy = 0.85 if signal == Signal.BUY else (0.10 if signal in (Signal.CLOSE, Signal.SELL) else 0.05)
                p_sell = 0.85 if signal in (Signal.CLOSE, Signal.SELL) else (0.10 if signal == Signal.BUY else 0.05)
                p_hold = 0.90 if signal == Signal.HOLD else 0.05
                probs = {"BUY": p_buy, "HOLD": p_hold, "SELL": p_sell}
                reason_str = f"{getattr(strategy, 'name', strat_name.upper())} generated {sig_str} at ${price:,.2f}"
                time_str = readable_time(latest.timestamp)
                print(f"[{time_str}] {strat_name.upper()} | Price: ${price:,.2f} | Signal: {sig_str} | Pos: {'OPEN' if position_open else 'FLAT'}", flush=True)

            last_action = None

            # 1. Check Intraday Stop-Loss / Take-Profit on Open Position
            if position_open and entry_price > 0:
                pnl_pct = (price - entry_price) / entry_price
                sl_pct = getattr(config, "STOP_LOSS", 0.015)
                tp_pct = getattr(config, "TAKE_PROFIT", 0.025)

                sl_hit = pnl_pct <= -sl_pct
                tp_hit = pnl_pct >= tp_pct

                if sl_hit or tp_hit:
                    reason_tag = "STOP_LOSS" if sl_hit else "TAKE_PROFIT"
                    console.print(f"[bold red]Executing TESTNET {reason_tag} for {position_size:.5f} BTC at ${price:,.2f}...[/bold red]")
                    fill = execute_order(adapter, "sell", round(position_size, 5), price)
                    exit_price = fill.fill_price
                    exit_fee = fill.fee_paid
                    total_fees += exit_fee
                    net_pnl = (exit_price - entry_price) * position_size - (entry_fee + exit_fee)
                    realized_pnl += net_pnl
                    if net_pnl > 0:
                        win_count += 1
                    else:
                        loss_count += 1
                    risk.record_trade_result(net_pnl)
                    risk.open_positions = max(0, risk.open_positions - 1)
                    risk.mark_trade_executed()
                    position_open = False
                    if hasattr(strategy, "_position_open"):
                        strategy._position_open = False
                    if hasattr(strategy, "reset_position"):
                        strategy.reset_position()

                    log_trade(
                        f"SELL ({reason_tag})",
                        readable_time(latest.timestamp),
                        exit_price,
                        position_size,
                        pnl=net_pnl,
                        confidence=conf_val,
                        reason=reason_tag,
                    )
                    last_action = {
                        "timestamp": readable_time(latest.timestamp),
                        "action": "SELL",
                        "price": exit_price,
                        "pnl": round(net_pnl, 2),
                        "order_id": fill.order_id,
                    }
                    actions_list.insert(0, last_action)

                    # Persist state
                    persisted["open_position"] = None
                    persisted["realized_pnl"] = realized_pnl
                    persisted["trade_count"] = trade_count
                    persisted["win_count"] = win_count
                    persisted["loss_count"] = loss_count
                    persisted["total_fees_paid"] = total_fees
                    persisted.setdefault("trade_history", []).append(last_action)
                    store.save(persisted)

                    position_size = 0.0
                    entry_price = 0.0

            # 2. BUY Order Execution
            if (signal == Signal.BUY or sig_str == "BUY") and not position_open and risk.can_open_position():
                capital = risk.position_size()
                if risk.check_min_notional(capital):
                    qty = round(capital / price, 5)
                    if qty >= 0.0001:
                        console.print(f"[bold green]Executing TESTNET BUY order for {qty:.5f} BTC...[/bold green]")
                        fill = execute_order(adapter, "buy", qty, price)
                        position_size = fill.filled_qty
                        entry_price = fill.fill_price
                        entry_fee = fill.fee_paid
                        total_fees += fill.fee_paid
                        position_open = True
                        trade_count += 1
                        risk.open_positions += 1
                        risk.mark_trade_executed()

                        log_trade(
                            "BUY",
                            readable_time(latest.timestamp),
                            fill.fill_price,
                            fill.filled_qty,
                            confidence=conf_val,
                            reason=reason_str,
                        )
                        last_action = {
                            "timestamp": readable_time(latest.timestamp),
                            "action": "BUY",
                            "price": fill.fill_price,
                            "order_id": fill.order_id,
                        }
                        actions_list.insert(0, last_action)

                        # Persist state
                        persisted["open_position"] = {
                            "entry_price": entry_price,
                            "size": position_size,
                            "entry_time": readable_time(latest.timestamp),
                            "entry_fee": entry_fee,
                            "order_id": fill.order_id,
                        }
                        persisted["trade_count"] = trade_count
                        persisted["total_fees_paid"] = total_fees
                        persisted.setdefault("trade_history", []).append(last_action)
                        store.save(persisted)

            # 3. SELL / CLOSE Order Execution
            elif (signal in (Signal.CLOSE, Signal.SELL) or sig_str in ("CLOSE", "SELL")) and position_open and risk.can_close_position():
                console.print(f"[bold red]Executing TESTNET SELL/CLOSE order for {position_size:.5f} BTC...[/bold red]")
                fill = execute_order(adapter, "sell", round(position_size, 5), price)
                exit_price = fill.fill_price
                exit_fee = fill.fee_paid
                total_fees += exit_fee
                net_pnl = (exit_price - entry_price) * position_size - (entry_fee + exit_fee)
                realized_pnl += net_pnl
                if net_pnl > 0:
                    win_count += 1
                else:
                    loss_count += 1

                risk.record_trade_result(net_pnl)
                risk.open_positions = max(0, risk.open_positions - 1)
                risk.mark_trade_executed()
                position_open = False
                if hasattr(strategy, "_position_open"):
                    strategy._position_open = False
                if hasattr(strategy, "reset_position"):
                    strategy.reset_position()

                log_trade(
                    "SELL",
                    readable_time(latest.timestamp),
                    exit_price,
                    position_size,
                    pnl=net_pnl,
                    confidence=conf_val,
                    reason=reason_str,
                )
                last_action = {
                    "timestamp": readable_time(latest.timestamp),
                    "action": "SELL",
                    "price": exit_price,
                    "pnl": round(net_pnl, 2),
                    "order_id": fill.order_id,
                }
                actions_list.insert(0, last_action)

                # Persist state
                persisted["open_position"] = None
                persisted["realized_pnl"] = realized_pnl
                persisted["trade_count"] = trade_count
                persisted["win_count"] = win_count
                persisted["loss_count"] = loss_count
                persisted["total_fees_paid"] = total_fees
                persisted.setdefault("trade_history", []).append(last_action)
                store.save(persisted)

                position_size = 0.0
                entry_price = 0.0

            # Push to dashboard
            unrealized = (price - entry_price) * position_size if position_open else 0.0
            state = {
                "symbol": args.symbol,
                "timeframe": args.timeframe,
                "price": price,
                "signal": sig_str,
                "confidence": conf_val,
                "probabilities": probs,
                "reason": reason_str,
                "balance": balance + realized_pnl,
                "starting_balance": balance,
                "realized_pnl": realized_pnl,
                "unrealized_pnl": unrealized,
                "position_open": position_open,
                "entry_price": entry_price,
                "position_size": position_size,
                "trade_count": trade_count,
                "win_count": win_count,
                "loss_count": loss_count,
                "total_fees_paid": total_fees,
                "last_action": last_action,
                "actions": list(actions_list[:20]),
            }
            emit_state(state)

            time.sleep(poll_interval)

        except KeyboardInterrupt:
            console.print("\n[yellow]Testnet loop stopped by user.[/yellow]")
            break
        except Exception as e:
            console.print(f"[red]Error in testnet loop: {e}. Retrying in 3s...[/red]")
            time.sleep(3)


# ===========================================================================
# 4. LEGACY POLLING MODE (BACKWARD COMPATIBLE)
# ===========================================================================

def run_polling(args: argparse.Namespace) -> None:
    if not config.validate_keys():
        return

    try:
        strategy = get_strategy(_strategy_name)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    adapter = BinanceTestnetAdapter(config.API_KEY, config.API_SECRET, symbol=config.SYMBOL)
    starting_balance = adapter.fetch_balance("USDT")
    min_notional = adapter.get_min_notional()
    risk = RiskManager(
        starting_balance=starting_balance,
        config=RiskConfig(min_notional=min_notional),
    )
    position_size = 0.0
    entry_price = 0.0
    entry_fee = 0.0

    print(f"Starting bot on {config.SYMBOL} | strategy: {strategy.name} | balance: {starting_balance:.2f} USDT")

    if not getattr(args, "no_dashboard", False):
        try:
            d_server = DashboardServer()
            d_server.start(open_browser=not getattr(args, "no_browser", False))
            time.sleep(1.0)
        except Exception as err:
            console.print(f"[yellow]Dashboard notice: {err}[/yellow]")

    for candle in adapter.fetch_candles(timeframe=config.TIMEFRAME, limit=50):
        strategy.history.append(candle)

    while True:
        try:
            candles = adapter.fetch_candles(timeframe=config.TIMEFRAME, limit=1)
            latest = candles[-1]
            signal = strategy.update(latest)

            candle_time = readable_time(latest.timestamp)
            print(f"[{candle_time}] price={latest.close:.2f} signal={signal.value}")

            emit_state({
                "price": latest.close,
                "signal": str(signal.name if hasattr(signal, "name") else signal),
                "realized_pnl": risk.daily_pnl if hasattr(risk, "daily_pnl") else 0.0,
                "trade_count": getattr(risk, "trades_count", 0),
                "position_open": position_size > 0,
                "position_size": position_size,
                "entry_price": entry_price,
                "balance": starting_balance,
                "symbol": config.SYMBOL,
            })

            if signal == Signal.BUY and risk.can_open_position():
                capital = risk.position_size()
                if not risk.check_min_notional(capital):
                    time.sleep(config.POLL_SECONDS)
                    continue
                size = capital / latest.close

                if config.DRY_RUN:
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
                if config.DRY_RUN:
                    exit_price = latest.close
                    exit_fee = position_size * latest.close * 0.001
                    gross_pnl = (exit_price - entry_price) * position_size
                    net_pnl = gross_pnl - (entry_fee + exit_fee)
                    risk.record_trade_result(net_pnl)
                    risk.open_positions -= 1
                    risk.mark_trade_executed()
                    log_trade("SELL (DRY)", now_str(), exit_price, position_size, pnl=net_pnl)
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
                    log_trade("SELL", now_str(), exit_price, position_size, pnl=net_pnl)
                    print(f"  -> [{now_str()}] SELL/CLOSE order: {fill.order_id} at {exit_price:.2f} | Net P&L: {net_pnl:+.2f} USDT (fees: {entry_fee + exit_fee:.4f})")
                    position_size = 0.0
                    entry_price = 0.0
                    entry_fee = 0.0

            time.sleep(config.POLL_SECONDS)

        except KeyboardInterrupt:
            print("Stopped by user.")
            break
        except Exception as e:
            print(f"Error: {e} -- retrying in 10s")
            time.sleep(10)


# ===========================================================================
# CLI DISPATCHER
# ===========================================================================

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Autonomous ML & Multi-Strategy Trading Bot")
    parser.add_argument(
        "mode_pos",
        nargs="?",
        default=None,
        help="Operating mode: backtest, replay, testnet, or polling (positional)",
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["backtest", "replay", "testnet", "polling"],
        default=None,
        help="Operating mode: backtest, replay, testnet, or polling (default: testnet)",
    )
    parser.add_argument(
        "--strategy", "-s",
        type=str,
        default="ml",
        help="Strategy to run: ml, tick, bollinger, rsi, sma, ema, macd (default: ml)",
    )
    parser.add_argument("--symbol", type=str, default=getattr(config, "ML_SYMBOL", "BTC/USDT"), help="Symbol pair")
    parser.add_argument("--timeframe", type=str, default=getattr(config, "ML_TIMEFRAME", "1m"), help="Timeframe (default: 1m)")
    parser.add_argument("--days", type=int, default=30, help="Days of historical data")
    parser.add_argument("--candles", type=int, default=60, help="Number of candles for replay")
    parser.add_argument("--delay", type=float, default=0.2, help="Delay between replay steps in seconds")
    parser.add_argument("--confidence", type=float, default=getattr(config, "ML_MIN_CONFIDENCE", 0.35), help="Minimum confidence threshold")
    parser.add_argument("--model-path", type=str, default=getattr(config, "ML_MODEL_PATH", "models/ml_model.joblib"), help="Model file path")
    parser.add_argument("--interval", type=int, default=3, help="Polling interval in seconds for live mode (default: 3)")
    parser.add_argument("--no-dashboard", action="store_true", help="Disable web dashboard")
    parser.add_argument("--no-browser", action="store_true", help="Do not automatically launch browser")

    args = parser.parse_args(argv)
    mode = (args.mode_pos or args.mode or os.getenv("TRADING_MODE", "testnet")).lower()

    if mode == "backtest":
        run_backtest(args)
    elif mode == "replay":
        run_replay(args)
    elif mode == "testnet":
        run_testnet(args)
    elif mode == "polling":
        run_polling(args)
    else:
        parser.print_help()


def run(mode: str = "polling") -> None:
    """Unified entry point for run.py launcher."""
    argv = ["--mode", mode]
    for i, a in enumerate(sys.argv):
        if a in ("--symbol", "--strategy", "-s", "--timeframe", "--interval", "--delay") and i + 1 < len(sys.argv):
            argv.extend([a, sys.argv[i+1]])
        elif a in ("--no-dashboard", "--no-browser"):
            argv.append(a)
    main(argv)


if __name__ == "__main__":
    main()