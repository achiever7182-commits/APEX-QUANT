"""
backtester/engine.py — Core backtesting engine.

Feeds historical candles through any Strategy, simulates trades using the
RiskManager rules, and collects every trade for analysis.

Assumptions:
- Fills happen at candle close price (conservative estimate)
- A flat fee of 0.1% per trade (Binance taker fee by default)
- No partial fills, no slippage beyond the fee assumption
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.strategy import Strategy, Signal, MarketData
from core.risk_manager import RiskManager, RiskConfig


FEE_RATE = 0.001  # 0.1% per trade (Binance taker)


@dataclass
class Trade:
    entry_price: float
    exit_price: float
    size: float
    entry_time: int   # ms timestamp
    exit_time: int
    pnl: float        # net of fees
    fee: float


@dataclass
class BacktestResult:
    trades: list[Trade]
    equity_curve: list[float]   # portfolio value after each candle
    candle_timestamps: list[int]
    starting_balance: float
    final_balance: float
    strategy_name: str
    symbol: str
    timeframe: str
    candle_count: int


class BacktestEngine:
    """
    Runs a strategy over a list of MarketData candles and produces a BacktestResult.

    Usage:
        engine = BacktestEngine(starting_balance=10_000)
        result = engine.run(strategy, candles)
    """

    def __init__(
        self,
        starting_balance: float = 10_000.0,
        fee_rate: float = FEE_RATE,
        risk_config: RiskConfig | None = None,
        symbol: str = "BTC/USDT",
        timeframe: str = "1m",
    ) -> None:
        self.starting_balance = starting_balance
        self.fee_rate = fee_rate
        self.risk_config = risk_config or RiskConfig(min_seconds_between_trades=0.0)
        self.symbol = symbol
        self.timeframe = timeframe

    def run(self, strategy: Strategy, candles: list[MarketData]) -> BacktestResult:
        balance = self.starting_balance
        risk = RiskManager(starting_balance=balance, config=self.risk_config)

        trades: list[Trade] = []
        equity_curve: list[float] = []
        timestamps: list[int] = []

        position_open = False
        entry_price = 0.0
        entry_time = 0
        position_size = 0.0
        unrealized_pnl = 0.0

        for candle in candles:
            signal = strategy.update(candle)
            price = candle.close

            # Track unrealized P&L on open position
            if position_open:
                unrealized_pnl = (price - entry_price) * position_size

            # --- BUY ---
            if signal == Signal.BUY and not position_open and risk.can_open_position():
                capital = risk.position_size()
                fee = capital * self.fee_rate
                capital_after_fee = capital - fee
                position_size = capital_after_fee / price
                entry_price = price
                entry_time = candle.timestamp
                position_open = True
                risk.open_positions += 1
                risk.mark_trade_executed()
                balance -= fee  # fee is deducted at entry

            # --- CLOSE ---
            elif signal == Signal.CLOSE and position_open:
                exit_price = price
                gross_pnl = (exit_price - entry_price) * position_size
                exit_fee = exit_price * position_size * self.fee_rate
                net_pnl = gross_pnl - exit_fee
                balance += net_pnl
                risk.record_trade_result(net_pnl)
                risk.open_positions -= 1
                risk.mark_trade_executed()
                trades.append(Trade(
                    entry_price=entry_price,
                    exit_price=exit_price,
                    size=position_size,
                    entry_time=entry_time,
                    exit_time=candle.timestamp,
                    pnl=net_pnl,
                    fee=exit_fee,
                ))
                position_open = False
                unrealized_pnl = 0.0

            # Equity = cash balance + open position value
            open_value = (price - entry_price) * position_size if position_open else 0.0
            equity_curve.append(balance + open_value)
            timestamps.append(candle.timestamp)

        # Force-close any open position at end of backtest
        if position_open and candles:
            last_price = candles[-1].close
            gross_pnl = (last_price - entry_price) * position_size
            exit_fee = last_price * position_size * self.fee_rate
            net_pnl = gross_pnl - exit_fee
            balance += net_pnl
            trades.append(Trade(
                entry_price=entry_price,
                exit_price=last_price,
                size=position_size,
                entry_time=entry_time,
                exit_time=candles[-1].timestamp,
                pnl=net_pnl,
                fee=exit_fee,
            ))

        return BacktestResult(
            trades=trades,
            equity_curve=equity_curve,
            candle_timestamps=timestamps,
            starting_balance=self.starting_balance,
            final_balance=balance,
            strategy_name=strategy.name,
            symbol=self.symbol,
            timeframe=self.timeframe,
            candle_count=len(candles),
        )
