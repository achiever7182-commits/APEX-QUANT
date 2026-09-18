"""
execution/paper_engine.py — Production-Grade Paper Trading Engine Coordinator.

Integrates the full quantitative pipeline:
  Market Data
      ↓
  Market Calendar
      ↓
  Data Safety Adapter
      ↓
  Feature Engineering (Step 4)
      ↓
  Walk-Forward ML Training (Step 5, strictly <= T)
      ↓
  Stock Ranking (Step 6 CrossSectionalRanker)
      ↓
  Portfolio Construction (Step 7 PortfolioBuilder)
      ↓
  Pre-Trade Risk Engine (Step 9D PaperRiskManager)
      ↓
  Order Manager (Step 9A)
      ↓
  Paper Broker (Step 9A/9I)
      ↓
  Paper Accounting (Step 9B)
      ↓
  Reconciliation (Step 9F)
      ↓
  Atomic Persistence (Step 9G)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union
import pandas as pd

from backtesting.walk_forward import WalkForwardMLTrainer
from execution.data_adapter import MarketDataSafetyAdapter, SignalContext, ValidatedQuote
from execution.models import (
    OrderSide,
    OrderStatus,
    OrderType,
    PaperAccount,
    PaperAuditEvent,
    PaperOrder,
    PaperPosition,
    ReconciliationReport,
)
from execution.order_manager import OrderManager
from execution.paper_broker import PaperBroker
from execution.persistence import PaperStatePersistence
from execution.reconciliation import ReconciliationEngine
from portfolio.models import PortfolioBuildResult, PortfolioPosition
from backtesting.portfolio_runner import PortfolioRunner
from backtesting.signal_runner import SignalRunner
from risk.kill_switch import PersistentKillSwitch
from risk.paper_risk_manager import PaperRiskManager

logger = logging.getLogger(__name__)


class PaperTradingEngine:
    """Production coordinator for simulated paper trading on Indian equities."""

    def __init__(
        self,
        initial_capital: float = 1_000_000.0,
        data_dir: str = "data/paper",
        transaction_cost_bps: float = 10.0,
        slippage_bps: float = 5.0,
        max_single_stock_weight: float = 0.35,
        max_sector_weight: float = 0.55,
        max_staleness_seconds: float = 300.0,
        auto_load_state: bool = True,
    ):
        self.initial_capital: float = initial_capital
        self.data_dir: str = data_dir

        # 1. Persistence & Kill Switch
        self.persistence: PaperStatePersistence = PaperStatePersistence(data_dir=data_dir)
        self.kill_switch: PersistentKillSwitch = PersistentKillSwitch(
            persistence_path=f"{data_dir}/kill_switch.json"
        )

        # 2. Market Data Safety
        self.data_adapter: MarketDataSafetyAdapter = MarketDataSafetyAdapter(
            max_staleness_seconds=max_staleness_seconds
        )

        # 3. Execution & Accounting
        self.broker: PaperBroker = PaperBroker(
            initial_capital=initial_capital,
            transaction_cost_bps=transaction_cost_bps,
            slippage_bps=slippage_bps,
        )

        # 4. Risk Engine
        self.risk_manager: PaperRiskManager = PaperRiskManager(
            kill_switch=self.kill_switch,
            data_adapter=self.data_adapter,
            max_single_stock_weight=max_single_stock_weight,
            max_sector_weight=max_sector_weight,
            transaction_fee_rate=transaction_cost_bps / 10_000.0,
            slippage_rate=slippage_bps / 10_000.0,
        )

        # 5. Order Manager
        self.order_manager: OrderManager = OrderManager(
            broker=self.broker,
            risk_manager=self.risk_manager,
            event_callback=self._on_audit_event,
        )

        # 6. Strategy Components
        self.signal_runner: SignalRunner = SignalRunner()
        self.portfolio_runner: PortfolioRunner = PortfolioRunner()
        self.wf_trainer: WalkForwardMLTrainer = WalkForwardMLTrainer(
            target_horizon=5, min_train_samples=100, model_type="ridge"
        )

        # 7. Internal Audit & Telemetry
        self.latest_reconciliation: Optional[ReconciliationReport] = None
        self.last_rebalance_timestamp: Optional[str] = None

        # 8. Resume State if present
        if auto_load_state and self.persistence.state_exists():
            self._restore_persisted_state()

    def _on_audit_event(self, event: PaperAuditEvent) -> None:
        """Handle structured audit events."""
        try:
            self.persistence.append_event(event)
        except Exception as e:
            logger.error("Failed to append paper audit event: %s", e)

    def _restore_persisted_state(self) -> None:
        """Restore account, positions, and orders from disk on restart."""
        try:
            account, positions, orders, fills = self.persistence.load_state()
            if account is not None:
                self.broker.accounting.account = account
                self.broker.accounting.positions = positions
                self.broker.accounting.fills_history = fills
                self.broker.orders = orders
                self.broker.fills = fills
                self.order_manager.orders = orders

                # Register existing idempotency keys into risk manager
                for ord_obj in orders.values():
                    if ord_obj.idempotency_key:
                        self.risk_manager.register_idempotency_key(ord_obj.idempotency_key)

                # Run startup reconciliation
                self.reconcile_state()
                self._on_audit_event(
                    PaperAuditEvent(
                        event_type="STATE_RESTORED",
                        payload={
                            "equity": account.total_equity,
                            "cash": account.cash,
                            "positions_count": len(positions),
                            "orders_count": len(orders),
                            "fills_count": len(fills),
                        },
                    )
                )
        except Exception as e:
            logger.error("Error restoring paper trading state: %s", e)

    def save_state(self) -> None:
        """Atomically persist current state to disk."""
        self.persistence.save_state(
            account=self.broker.get_account(),
            positions=self.broker.get_positions(),
            orders=self.order_manager.orders,
            fills=self.broker.get_fills(),
        )

    def reconcile_state(
        self, expected_targets: Optional[Dict[str, Any]] = None, expected_cash: Optional[float] = None
    ) -> ReconciliationReport:
        """Execute reconciliation audit."""
        account = self.broker.get_account()
        positions = self.broker.get_positions()
        fills = self.broker.get_fills()

        report = ReconciliationEngine.reconcile(
            account=account,
            positions=positions,
            fills=fills,
            expected_targets=expected_targets,
            expected_cash=expected_cash,
        )
        self.latest_reconciliation = report

        event_type = "RECONCILIATION_MATCH" if report.is_clean else "RECONCILIATION_MISMATCH"
        level = "INFO" if report.is_clean else "WARNING"
        self._on_audit_event(
            PaperAuditEvent(
                event_type=event_type,
                level=level,
                payload={
                    "status": report.status.value,
                    "is_clean": report.is_clean,
                    "discrepancies_count": len(report.discrepancies),
                },
            )
        )
        return report

    def execute_rebalance(
        self,
        candidate_panel: pd.DataFrame,
        market_bars_history: Dict[str, pd.DataFrame],
        current_quotes: Dict[str, float],
        current_volumes: Optional[Dict[str, float]] = None,
        as_of_time: Optional[Union[datetime, pd.Timestamp]] = None,
        allocation_method: str = "constrained",
    ) -> Dict[str, Any]:
        """
        Execute full quantitative rebalance pipeline:
        Features -> Walk-forward ML -> Ranking -> Portfolio Builder -> Pre-Trade Risk -> Orders -> Fills -> Accounting.
        """
        t = as_of_time or pd.Timestamp.now(tz="UTC")
        if not isinstance(t, pd.Timestamp):
            t = pd.to_datetime(t, utc=True)

        t_str = t.isoformat()
        self.last_rebalance_timestamp = t_str

        # 1. Update Market Panel
        self.broker.update_market_panel(current_quotes, current_volumes)

        # 2. Walk-Forward ML Prediction strictly on data <= T
        pit_panel = self.wf_trainer.train_and_predict(
            candidate_panel=candidate_panel,
            as_of_time=t,
        )

        # 3. Cross-Sectional Ranking (Step 6)
        ranked_universe = self.signal_runner.generate_ranking(
            candidate_panel=pit_panel,
            as_of_time=t,
        )

        # 4. Target Portfolio Construction (Step 7)
        account = self.broker.get_account()
        current_holdings = {
            sym: PortfolioPosition(
                symbol=p.symbol,
                shares=p.shares,
                price=p.current_price,
                value=p.market_value,
                weight=p.market_value / account.total_equity if account.total_equity > 0 else 0.0,
            )
            for sym, p in self.broker.get_positions().items()
        }

        build_result: PortfolioBuildResult = self.portfolio_runner.build_target_portfolio(
            ranked_universe=ranked_universe,
            market_bars_history=market_bars_history,
            total_capital=account.total_equity,
            current_holdings=current_holdings,
            method=allocation_method,
        )

        # 5. Order Generation (SELLs first to liberate cash, then BUYs)
        current_shares_map = {sym: p.shares for sym, p in self.broker.get_positions().items()}
        target_shares_map = {sym: tgt.target_shares for sym, tgt in build_result.positions.items()}

        all_symbols = set(current_shares_map.keys()).union(target_shares_map.keys())
        sell_orders: List[PaperOrder] = []
        buy_orders: List[PaperOrder] = []

        rebal_id = f"REBAL-{t.strftime('%Y%m%d%H%M%S')}"

        for sym in sorted(all_symbols):
            c_shares = current_shares_map.get(sym, 0)
            t_shares = target_shares_map.get(sym, 0)
            delta = t_shares - c_shares

            if delta < 0:
                sell_orders.append(
                    PaperOrder(
                        symbol=sym,
                        side=OrderSide.SELL,
                        order_type=OrderType.MARKET,
                        requested_quantity=abs(delta),
                        idempotency_key=f"{rebal_id}-{sym}-SELL",
                        metadata={"rebalance_id": rebal_id},
                    )
                )
            elif delta > 0:
                buy_orders.append(
                    PaperOrder(
                        symbol=sym,
                        side=OrderSide.BUY,
                        order_type=OrderType.MARKET,
                        requested_quantity=delta,
                        idempotency_key=f"{rebal_id}-{sym}-BUY",
                        metadata={"rebalance_id": rebal_id},
                    )
                )

        executed_orders: List[PaperOrder] = []

        # Execute SELLs first
        for s_order in sell_orders:
            px = current_quotes.get(s_order.symbol, 0.0)
            vol = current_volumes.get(s_order.symbol, 0.0) if current_volumes else 0.0
            val_quote = self.data_adapter.validate_quote(
                symbol=s_order.symbol, price=px, volume=vol, reference_time=t
            )
            exec_order = self.order_manager.submit_order(
                order=s_order, quote=val_quote, reference_volume=vol, as_of_time=t
            )
            executed_orders.append(exec_order)

        # Execute BUYs second
        for b_order in buy_orders:
            px = current_quotes.get(b_order.symbol, 0.0)
            vol = current_volumes.get(b_order.symbol, 0.0) if current_volumes else 0.0
            val_quote = self.data_adapter.validate_quote(
                symbol=b_order.symbol, price=px, volume=vol, reference_time=t
            )
            exec_order = self.order_manager.submit_order(
                order=b_order, quote=val_quote, reference_volume=vol, as_of_time=t
            )
            executed_orders.append(exec_order)

        # 6. Post-Rebalance Reconciliation & Persistence
        recon_report = self.reconcile_state(
            expected_targets=build_result.positions,
            expected_cash=build_result.cash,
        )
        self.save_state()

        return {
            "rebalance_id": rebal_id,
            "timestamp": t_str,
            "allocation_method": build_result.allocation_method,
            "total_orders": len(executed_orders),
            "filled_orders": sum(1 for o in executed_orders if o.status == OrderStatus.FILLED),
            "partially_filled_orders": sum(1 for o in executed_orders if o.status == OrderStatus.PARTIALLY_FILLED),
            "rejected_orders": sum(1 for o in executed_orders if o.status == OrderStatus.REJECTED),
            "account": self.broker.get_account().to_dict(),
            "reconciliation": recon_report.to_dict(),
        }

    def get_telemetry_summary(self) -> Dict[str, Any]:
        """Get structured telemetry for dashboard monitoring."""
        acct = self.broker.get_account()
        positions = self.broker.get_positions()
        is_mkt_open = self.data_adapter.is_market_open()

        return {
            "mode": "PAPER_TRADING",
            "market_open": is_mkt_open,
            "kill_switch": self.kill_switch.get_status(),
            "initial_capital": acct.initial_capital,
            "cash": acct.cash,
            "positions_value": acct.positions_value,
            "total_equity": acct.total_equity,
            "daily_pnl": acct.daily_pnl,
            "realized_pnl": acct.realized_pnl,
            "unrealized_pnl": acct.unrealized_pnl,
            "total_fees": acct.total_fees,
            "total_slippage": acct.total_slippage,
            "max_drawdown": acct.max_drawdown,
            "positions_count": len(positions),
            "positions": [p.to_dict() for p in positions.values()],
            "last_reconciliation": self.latest_reconciliation.to_dict() if self.latest_reconciliation else None,
            "last_updated": acct.last_updated,
        }
