"""
core/risk_manager.py

Non-negotiable safety layer. The strategy can WANT to buy/sell, but the
risk manager has final veto power. This is what prevents a buggy strategy
or a bad market move from blowing up the account.
"""

from dataclasses import dataclass
import time


@dataclass
class RiskConfig:
    max_position_size_pct: float = 0.02      # max 2% of balance per trade
    max_daily_loss_pct: float = 0.05          # stop trading after 5% daily loss
    stop_loss_pct: float = 0.01               # 1% stop-loss per trade
    take_profit_pct: float = 0.02             # 2% take-profit per trade
    max_open_positions: int = 3
    min_seconds_between_trades: float = 15.0  # cooldown -- prevents fee-burning overtrading while allowing active trading
    min_notional: float = 10.0                # minimum order value in quote currency (USDT)


class RiskManager:
    def __init__(self, starting_balance: float, config: RiskConfig = None):
        self.balance = starting_balance
        self.starting_balance = starting_balance
        self.config = config or RiskConfig()
        self.daily_pnl = 0.0
        self.open_positions = 0
        self.trading_halted = False
        self.last_trade_time = 0.0

    def can_open_position(self) -> bool:
        if self.trading_halted:
            return False
        if self.balance <= 0 or self.starting_balance <= 0:
            return False
        if self.open_positions >= self.config.max_open_positions:
            return False
        if time.time() - self.last_trade_time < self.config.min_seconds_between_trades:
            return False  # still cooling down since the last trade
        daily_loss_pct = (
            -self.daily_pnl / self.starting_balance
            if (self.daily_pnl < 0 and self.starting_balance > 0)
            else 0.0
        )
        if daily_loss_pct >= self.config.max_daily_loss_pct:
            self.trading_halted = True
            return False
        return True

    def can_close_position(self) -> bool:
        """Verify an open position exists and trade cooldown has expired before closing."""
        if self.open_positions <= 0:
            return False
        if time.time() - self.last_trade_time < self.config.min_seconds_between_trades:
            return False  # still cooling down since the last trade
        return True

    def mark_trade_executed(self):
        self.last_trade_time = time.time()

    def position_size(self) -> float:
        """Returns how much capital to risk on the next trade in quote currency (USDT)."""
        return self.balance * self.config.max_position_size_pct

    def check_min_notional(self, order_value: float) -> bool:
        """
        Verify that calculated order value (size * price) meets Binance minimum notional.
        If below threshold, logs a skip message and returns False.
        """
        if order_value < self.config.min_notional:
            print(
                f"[SKIP] Order value ${order_value:.2f} is below Binance minimum notional "
                f"(${self.config.min_notional:.2f}) -- increase starting balance or position_size_pct."
            )
            return False
        return True


    def stop_loss_price(self, entry_price: float, is_long: bool) -> float:
        if is_long:
            return entry_price * (1 - self.config.stop_loss_pct)
        return entry_price * (1 + self.config.stop_loss_pct)

    def take_profit_price(self, entry_price: float, is_long: bool) -> float:
        if is_long:
            return entry_price * (1 + self.config.take_profit_pct)
        return entry_price * (1 - self.config.take_profit_pct)

    def record_trade_result(self, pnl: float):
        self.daily_pnl += pnl
        self.balance += pnl

    def reset_daily(self):
        self.daily_pnl = 0.0
        self.trading_halted = False
