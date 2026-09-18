"""
risk/paper_risk_manager.py — 12-Point Pre-Trade Risk Engine for Paper Trading.

Performs strict pre-trade validation before any order can be dispatched:
  1. Persistent kill switch
  2. Duplicate order protection (idempotency keys)
  3. Market status (NSE market hours & trading days)
  4. Data freshness (max 300s quote staleness)
  5. Daily loss limit (e.g. -3.0% daily decline)
  6. Maximum drawdown limit (e.g. -10.0% peak-to-trough)
  7. Sell share balance check (ensures owned shares >= sell quantity, no shorting)
  8. Available cash check (ensures cash >= buy notional + fees)
  9. Liquidity limit (max 5% of rolling historical volume)
  10. Position size limit (max 35% single-stock)
  11. Sector exposure limit (max 55% sector)
  12. Total gross exposure limit (max 100%, zero leverage)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, Optional, Set
import pandas as pd

from execution.data_adapter import MarketDataSafetyAdapter, ValidatedQuote
from execution.models import OrderSide, PaperAccount, PaperOrder, PaperPosition, RejectionReason
from risk.kill_switch import PersistentKillSwitch


@dataclass
class RiskCheckResult:
    """Result of pre-trade risk evaluation."""
    passed: bool
    rejection_reason: Optional[RejectionReason] = None
    details: str = ""
    metrics: Dict[str, Any] = None


class PaperRiskManager:
    """Evaluates 11 pre-trade risk checks against account state and market conditions."""

    def __init__(
        self,
        kill_switch: Optional[PersistentKillSwitch] = None,
        data_adapter: Optional[MarketDataSafetyAdapter] = None,
        max_single_stock_weight: float = 0.35,
        max_sector_weight: float = 0.55,
        max_gross_exposure: float = 1.00,
        max_daily_loss_fraction: float = 0.03,  # -3.0%
        max_drawdown_fraction: float = 0.10,    # -10.0%
        liquidity_limit_fraction: float = 0.05, # 5.0% of volume
        transaction_fee_rate: float = 0.0010,   # 10 bps
        slippage_rate: float = 0.0005,          # 5 bps
        sector_lookup: Optional[Dict[str, str]] = None,
    ):
        self.kill_switch: PersistentKillSwitch = kill_switch or PersistentKillSwitch()
        self.data_adapter: MarketDataSafetyAdapter = data_adapter or MarketDataSafetyAdapter()
        self.max_single_stock_weight: float = max_single_stock_weight
        self.max_sector_weight: float = max_sector_weight
        self.max_gross_exposure: float = max_gross_exposure
        self.max_daily_loss_fraction: float = max_daily_loss_fraction
        self.max_drawdown_fraction: float = max_drawdown_fraction
        self.liquidity_limit_fraction: float = liquidity_limit_fraction
        self.transaction_fee_rate: float = transaction_fee_rate
        self.slippage_rate: float = slippage_rate
        self.sector_lookup: Dict[str, str] = sector_lookup or {
            "RELIANCE": "Energy",
            "TCS": "Technology",
            "INFY": "Technology",
            "HDFCBANK": "Financials",
            "ICICIBANK": "Financials",
        }
        self._processed_idempotency_keys: Set[str] = set()

    def evaluate_order(
        self,
        order: PaperOrder,
        account: PaperAccount,
        positions: Dict[str, PaperPosition],
        quote: ValidatedQuote,
        reference_volume: Optional[float] = None,
        as_of_time: Optional[Any] = None,
    ) -> RiskCheckResult:
        """
        Run all 12 pre-trade risk checks sequentially.
        """
        # 1. Kill Switch Check
        if self.kill_switch.is_active():
            return RiskCheckResult(
                passed=False,
                rejection_reason=RejectionReason.KILL_SWITCH,
                details=f"Persistent kill switch engaged: {self.kill_switch.state.reason}",
            )

        # 2. Duplicate Order Protection (Idempotency Key)
        if order.idempotency_key:
            if order.idempotency_key in self._processed_idempotency_keys:
                return RiskCheckResult(
                    passed=False,
                    rejection_reason=RejectionReason.DUPLICATE_ORDER,
                    details=f"Order with idempotency key '{order.idempotency_key}' was already processed",
                )

        # 3. Market Status Check
        if not self.data_adapter.is_market_open(as_of_time):
            return RiskCheckResult(
                passed=False,
                rejection_reason=RejectionReason.MARKET_CLOSED,
                details="NSE market is currently closed (outside trading hours or holiday/weekend)",
            )

        # 4. Data Freshness Check
        if not quote.is_valid:
            return RiskCheckResult(
                passed=False,
                rejection_reason=RejectionReason.STALE_DATA,
                details=f"Market quote rejected: {quote.rejection_reason} (age: {quote.data_age_seconds:.1f}s)",
            )

        # 5. Daily Loss Limit Check
        if account.start_of_day_equity > 0:
            daily_loss_fraction = (account.start_of_day_equity - account.total_equity) / account.start_of_day_equity
            if daily_loss_fraction >= self.max_daily_loss_fraction and order.side == OrderSide.BUY:
                return RiskCheckResult(
                    passed=False,
                    rejection_reason=RejectionReason.DAILY_LOSS_LIMIT,
                    details=f"Daily loss limit breached: {daily_loss_fraction*100:.2f}% >= {self.max_daily_loss_fraction*100:.2f}%",
                )

        # 6. Drawdown Limit Check
        if account.max_drawdown >= self.max_drawdown_fraction and order.side == OrderSide.BUY:
            return RiskCheckResult(
                passed=False,
                rejection_reason=RejectionReason.DRAWDOWN_LIMIT,
                details=f"Maximum drawdown limit breached: {account.max_drawdown*100:.2f}% >= {self.max_drawdown_fraction*100:.2f}%",
            )

        # 7. Sell Share Balance Check (if SELL)
        if order.side == OrderSide.SELL:
            current_pos = positions.get(order.symbol)
            if current_pos is None or current_pos.shares < order.requested_quantity:
                owned = current_pos.shares if current_pos else 0
                return RiskCheckResult(
                    passed=False,
                    rejection_reason=RejectionReason.INSUFFICIENT_SHARES,
                    details=f"Requested sell {order.requested_quantity} shares, but own {owned} shares",
                )
            # Sells liberate cash and de-risk, so they pass remaining buy-side limits
            if order.idempotency_key:
                self._processed_idempotency_keys.add(order.idempotency_key)
            return RiskCheckResult(passed=True)

        # --- BUY Order Specific Checks ---
        exec_price = quote.price * (1.0 + self.slippage_rate)
        est_notional = order.requested_quantity * exec_price
        est_fee = est_notional * self.transaction_fee_rate
        est_total_cost = est_notional + est_fee

        # 8. Available Cash Check
        if est_total_cost > account.cash:
            return RiskCheckResult(
                passed=False,
                rejection_reason=RejectionReason.INSUFFICIENT_CASH,
                details=f"Estimated cost ₹{est_total_cost:,.2f} exceeds available cash ₹{account.cash:,.2f}",
            )

        # 9. Liquidity Limit Check
        ref_vol = reference_volume if reference_volume is not None else quote.volume
        if ref_vol > 0 and self.liquidity_limit_fraction > 0:
            max_liq_shares = int(math.floor(ref_vol * self.liquidity_limit_fraction))
            if max_liq_shares <= 0 or order.requested_quantity > max_liq_shares:
                return RiskCheckResult(
                    passed=False,
                    rejection_reason=RejectionReason.LIQUIDITY_LIMIT,
                    details=f"Requested {order.requested_quantity} shares exceeds 5% volume limit ({max_liq_shares} shares)",
                )

        # 10. Position Limit Check (Single-Stock <= 35%)
        curr_shares = positions[order.symbol].shares if order.symbol in positions else 0
        new_shares = curr_shares + order.requested_quantity
        post_stock_value = new_shares * quote.price
        post_weight = post_stock_value / account.total_equity if account.total_equity > 0 else 0.0

        if post_weight > (self.max_single_stock_weight + 0.005):
            return RiskCheckResult(
                passed=False,
                rejection_reason=RejectionReason.POSITION_LIMIT,
                details=f"Post-execution weight {post_weight*100:.2f}% exceeds single-stock limit {self.max_single_stock_weight*100:.2f}%",
            )

        # 11. Sector Exposure Limit Check (Sector <= 55%)
        sec = self.sector_lookup.get(order.symbol, "Unknown")
        current_sector_value = sum(
            p.market_value for s, p in positions.items()
            if self.sector_lookup.get(s, "Unknown") == sec
        )
        post_sec_value = current_sector_value + est_notional
        post_sec_weight = post_sec_value / account.total_equity if account.total_equity > 0 else 0.0

        if post_sec_weight > (self.max_sector_weight + 0.005):
            return RiskCheckResult(
                passed=False,
                rejection_reason=RejectionReason.SECTOR_LIMIT,
                details=f"Post-execution sector weight ({sec}) {post_sec_weight*100:.2f}% exceeds limit {self.max_sector_weight*100:.2f}%",
            )

        # 12. Total Gross Exposure Check (<= 100%, zero leverage)
        post_gross_exposure = (account.positions_value + est_notional) / account.total_equity if account.total_equity > 0 else 0.0
        if post_gross_exposure > (self.max_gross_exposure + 0.005):
            return RiskCheckResult(
                passed=False,
                rejection_reason=RejectionReason.TOTAL_EXPOSURE_LIMIT,
                details=f"Post-execution gross exposure {post_gross_exposure*100:.2f}% exceeds 100% (leverage forbidden)",
            )

        # Record idempotency key if passed
        if order.idempotency_key:
            self._processed_idempotency_keys.add(order.idempotency_key)

        return RiskCheckResult(passed=True)

    def register_idempotency_key(self, key: str) -> None:
        """Manually record an idempotency key (e.g. during restart recovery)."""
        if key:
            self._processed_idempotency_keys.add(key)
