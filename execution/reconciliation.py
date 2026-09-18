"""
execution/reconciliation.py — Portfolio Reconciliation & Discrepancy Auditor.

Performs deterministic reconciliation between:
  1. Expected Portfolio Targets (from Step 7 PortfolioBuilder) vs Actual Paper Broker Holdings.
  2. Double-Entry Accounting Ledger (Cash + sum(Market Values) == Total Equity).
  3. Fill History vs Account Cash Movement (Initial Cash - Buys + Sells - Fees == Current Cash).

Guarantees explicit audit reporting (MATCH, MISMATCH, ERROR) with zero silent mutations.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Dict, List, Optional
from execution.models import (
    OrderSide,
    OrderStatus,
    PaperAccount,
    PaperFill,
    PaperOrder,
    PaperPosition,
    ReconciliationDiscrepancy,
    ReconciliationReport,
    ReconciliationStatus,
)
from portfolio.models import PortfolioTarget

if TYPE_CHECKING:
    from execution.broker import Broker



class ReconciliationEngine:
    """Audits portfolio state and identifies execution, cash, or position mismatches."""

    @staticmethod
    def reconcile(
        account: PaperAccount,
        positions: Dict[str, PaperPosition],
        fills: List[PaperFill],
        expected_targets: Optional[Dict[str, PortfolioTarget]] = None,
        expected_cash: Optional[float] = None,
        tolerance: float = 1e-4,
    ) -> ReconciliationReport:
        """
        Execute full reconciliation audit.
        """
        discrepancies: List[ReconciliationDiscrepancy] = []
        now_str = datetime.now(timezone.utc).isoformat()

        # 1. Double-Entry Balance Identity Audit
        pos_val = sum(p.market_value for p in positions.values())
        calc_equity = account.cash + pos_val
        equity_diff = abs(calc_equity - account.total_equity)

        if equity_diff > tolerance:
            discrepancies.append(
                ReconciliationDiscrepancy(
                    category="BALANCE_IDENTITY",
                    symbol=None,
                    expected_value=calc_equity,
                    actual_value=account.total_equity,
                    difference=equity_diff,
                    details=f"Calculated equity (Cash {account.cash:.2f} + PosVal {pos_val:.2f}) != Account equity {account.total_equity:.2f}",
                )
            )

        # 2. Cash Reconciliation from Fills History
        net_fill_cash_flow = 0.0
        for f in fills:
            if f.side == OrderSide.BUY:
                net_fill_cash_flow -= (f.quantity * f.price) + f.transaction_cost
            elif f.side == OrderSide.SELL:
                net_fill_cash_flow += (f.quantity * f.price) - f.transaction_cost

        calc_expected_cash = account.initial_capital + net_fill_cash_flow
        cash_fill_diff = abs(calc_expected_cash - account.cash)
        if cash_fill_diff > tolerance:
            discrepancies.append(
                ReconciliationDiscrepancy(
                    category="CASH_FILL_AUDIT",
                    symbol=None,
                    expected_value=calc_expected_cash,
                    actual_value=account.cash,
                    difference=cash_fill_diff,
                    details=f"Initial capital ({account.initial_capital:,.2f}) + Fills net flow ({net_fill_cash_flow:,.2f}) != Current cash ({account.cash:,.2f})",
                )
            )

        # 3. Duplicate Fill Audit
        seen_fill_ids = set()
        for f in fills:
            if f.fill_id in seen_fill_ids:
                discrepancies.append(
                    ReconciliationDiscrepancy(
                        category="DUPLICATE_FILL",
                        symbol=f.symbol,
                        expected_value=1,
                        actual_value=2,
                        details=f"Duplicate fill ID detected: {f.fill_id}",
                    )
                )
            seen_fill_ids.add(f.fill_id)

        # 4. Expected Target Portfolio Comparison (if provided)
        if expected_targets is not None:
            all_symbols = set(positions.keys()).union(expected_targets.keys())
            for sym in sorted(all_symbols):
                act_shares = positions[sym].shares if sym in positions else 0
                exp_shares = expected_targets[sym].target_shares if sym in expected_targets else 0

                if act_shares != exp_shares:
                    discrepancies.append(
                        ReconciliationDiscrepancy(
                            category="TARGET_SHARES_MISMATCH",
                            symbol=sym,
                            expected_value=exp_shares,
                            actual_value=act_shares,
                            difference=float(act_shares - exp_shares),
                            details=f"Target shares {exp_shares} != Actual holding shares {act_shares}",
                        )
                    )

        # 5. Expected Cash Comparison (if provided)
        cash_difference = 0.0
        if expected_cash is not None:
            cash_difference = abs(account.cash - expected_cash)
            if cash_difference > tolerance:
                discrepancies.append(
                    ReconciliationDiscrepancy(
                        category="EXPECTED_CASH_MISMATCH",
                        symbol=None,
                        expected_value=expected_cash,
                        actual_value=account.cash,
                        difference=cash_difference,
                        details=f"Expected target cash {expected_cash:,.2f} != Actual cash {account.cash:,.2f}",
                    )
                )

        # Status determination
        if len(discrepancies) == 0:
            status = ReconciliationStatus.MATCH
            is_clean = True
        else:
            # Fatal error if double entry is broken, otherwise mismatch
            has_fatal = any(d.category in ("BALANCE_IDENTITY", "CASH_FILL_AUDIT", "DUPLICATE_FILL") for d in discrepancies)
            status = ReconciliationStatus.ERROR if has_fatal else ReconciliationStatus.MISMATCH
            is_clean = False

        return ReconciliationReport(
            timestamp=now_str,
            status=status,
            is_clean=is_clean,
            expected_equity=calc_equity,
            actual_equity=account.total_equity,
            cash_difference=cash_difference,
            discrepancies=discrepancies,
        )

    @staticmethod
    def reconcile_with_broker(
        local_account: PaperAccount,
        local_positions: Dict[str, PaperPosition],
        local_orders: Dict[str, PaperOrder],
        broker: Broker,
        tolerance: float = 1e-4,
    ) -> ReconciliationReport:
        """
        Audit internal portfolio state directly against external broker state.
        
        Detects:
          - Cash discrepancies
          - Position / share count discrepancies
          - Orphan orders at broker
          - Local orders missing or out-of-sync at broker
        """
        discrepancies: List[ReconciliationDiscrepancy] = []
        now_str = datetime.now(timezone.utc).isoformat()

        try:
            broker_account = broker.get_account()
            broker_positions = broker.get_positions()
            broker_orders_list = broker.get_orders()
            broker_orders = {o.order_id: o for o in broker_orders_list}
        except Exception as e:
            discrepancies.append(
                ReconciliationDiscrepancy(
                    category="BROKER_COMMUNICATION_ERROR",
                    symbol=None,
                    expected_value="SUCCESS",
                    actual_value="EXCEPTION",
                    details=f"Failed to query broker state: {str(e)}",
                )
            )
            return ReconciliationReport(
                timestamp=now_str,
                status=ReconciliationStatus.ERROR,
                is_clean=False,
                expected_equity=local_account.total_equity,
                actual_equity=0.0,
                cash_difference=0.0,
                discrepancies=discrepancies,
            )

        # 1. Cash Audit
        cash_diff = abs(local_account.cash - broker_account.cash)
        if cash_diff > tolerance:
            discrepancies.append(
                ReconciliationDiscrepancy(
                    category="BROKER_CASH_MISMATCH",
                    symbol=None,
                    expected_value=local_account.cash,
                    actual_value=broker_account.cash,
                    difference=cash_diff,
                    details=f"Local cash ({local_account.cash:,.2f}) != Broker cash ({broker_account.cash:,.2f})",
                )
            )

        # 2. Positions Audit
        all_symbols = set(local_positions.keys()).union(broker_positions.keys())
        for sym in sorted(all_symbols):
            local_sh = local_positions[sym].shares if sym in local_positions else 0
            broker_sh = broker_positions[sym].shares if sym in broker_positions else 0
            if local_sh != broker_sh:
                discrepancies.append(
                    ReconciliationDiscrepancy(
                        category="BROKER_POSITION_MISMATCH",
                        symbol=sym,
                        expected_value=local_sh,
                        actual_value=broker_sh,
                        difference=float(broker_sh - local_sh),
                        details=f"Local shares ({local_sh}) != Broker shares ({broker_sh}) for {sym}",
                    )
                )

        # 3. Orders Audit
        # Check orphan orders at broker
        for b_id, b_ord in broker_orders.items():
            if b_id not in local_orders:
                discrepancies.append(
                    ReconciliationDiscrepancy(
                        category="BROKER_ORDER_ORPHAN",
                        symbol=b_ord.symbol,
                        expected_value=None,
                        actual_value=b_id,
                        details=f"Order {b_id} exists at broker but missing in local state",
                    )
                )

        # Check local orders status vs broker
        for l_id, l_ord in local_orders.items():
            if l_ord.status in (OrderStatus.SUBMITTED, OrderStatus.ACCEPTED, OrderStatus.FILLED):
                if l_id not in broker_orders:
                    discrepancies.append(
                        ReconciliationDiscrepancy(
                            category="LOCAL_ORDER_MISSING_AT_BROKER",
                            symbol=l_ord.symbol,
                            expected_value=l_id,
                            actual_value=None,
                            details=f"Local order {l_id} in state {l_ord.status.value} not found at broker",
                        )
                    )
                else:
                    b_ord = broker_orders[l_id]
                    if b_ord.status != l_ord.status:
                        discrepancies.append(
                            ReconciliationDiscrepancy(
                                category="BROKER_ORDER_STATUS_MISMATCH",
                                symbol=l_ord.symbol,
                                expected_value=l_ord.status.value,
                                actual_value=b_ord.status.value,
                                details=f"Local order status {l_ord.status.value} != Broker order status {b_ord.status.value}",
                            )
                        )
                    if b_ord.filled_quantity != l_ord.filled_quantity:
                        discrepancies.append(
                            ReconciliationDiscrepancy(
                                category="BROKER_ORDER_QUANTITY_MISMATCH",
                                symbol=l_ord.symbol,
                                expected_value=l_ord.filled_quantity,
                                actual_value=b_ord.filled_quantity,
                                details=f"Local filled quantity {l_ord.filled_quantity} != Broker filled quantity {b_ord.filled_quantity}",
                            )
                        )


        if len(discrepancies) == 0:
            status = ReconciliationStatus.MATCH
            is_clean = True
        else:
            status = ReconciliationStatus.MISMATCH
            is_clean = False

        return ReconciliationReport(
            timestamp=now_str,
            status=status,
            is_clean=is_clean,
            expected_equity=local_account.total_equity,
            actual_equity=broker_account.total_equity,
            cash_difference=cash_diff,
            discrepancies=discrepancies,
        )

