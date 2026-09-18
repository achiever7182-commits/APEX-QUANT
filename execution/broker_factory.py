"""
execution/broker_factory.py — Broker Factory with Strict Live Trading Safety Gate.

Instantiates broker adapters (PaperBroker, KiteBrokerAdapter) while enforcing
fail-closed validation that prevents accidental live execution.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from execution.broker import Broker
from execution.exceptions import LiveTradingDisabledError
from execution.paper_broker import PaperBroker
from execution.adapters.kite_adapter import KiteBrokerAdapter

logger = logging.getLogger(__name__)

SUPPORTED_BROKERS = ["paper", "kite", "zerodha"]


def get_supported_brokers() -> List[str]:
    """Return list of supported broker identifiers."""
    return list(SUPPORTED_BROKERS)


def create_broker(
    broker_type: str = "paper",
    trading_mode: str = "paper",
    initial_capital: float = 1_000_000.0,
    config: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> Broker:
    """
    Factory function to instantiate and configure an execution Broker.
    
    SAFETY ENFORCEMENT:
      If trading_mode is set to 'live', this factory unconditionally raises
      LiveTradingDisabledError. Live execution is strictly forbidden in Step 10.
    """
    mode_clean = trading_mode.strip().lower()
    if mode_clean in ("live", "production", "prod", "real", "broker", "true", "1"):
        raise LiveTradingDisabledError(
            f"Live/production trading mode '{trading_mode}' is strictly disabled in APEX QUANT Step 10. "
            "Cannot instantiate an execution broker.",
            broker_name=broker_type,
        )
    if mode_clean not in ("paper", "simulated", "backtest"):
        raise LiveTradingDisabledError(
            f"Unrecognized trading mode '{trading_mode}'. Fail-closed: only 'paper' mode is permitted.",
            broker_name=broker_type,
        )


    b_type = broker_type.strip().lower()
    cfg = config or {}

    if b_type in ("paper", "simulated"):
        tx_bps = kwargs.get("transaction_cost_bps", cfg.get("transaction_cost_bps", 10.0))
        slip_bps = kwargs.get("slippage_bps", cfg.get("slippage_bps", 5.0))
        liq_cap = kwargs.get("liquidity_participation_limit", cfg.get("liquidity_participation_limit", 0.05))
        
        logger.info(f"Instantiating PaperBroker with capital ₹{initial_capital:,.2f}")
        return PaperBroker(
            initial_capital=initial_capital,
            transaction_cost_bps=tx_bps,
            slippage_bps=slip_bps,
            liquidity_participation_limit=liq_cap,
        )

    elif b_type in ("kite", "zerodha"):
        mock_mode = kwargs.get("mock_mode", cfg.get("mock_mode", False))
        api_key = kwargs.get("api_key", cfg.get("api_key"))
        access_token = kwargs.get("access_token", cfg.get("access_token"))

        logger.info(f"Instantiating KiteBrokerAdapter (mock_mode={mock_mode})")
        return KiteBrokerAdapter(
            api_key=api_key,
            access_token=access_token,
            mock_mode=mock_mode,
            config=cfg,
        )

    else:
        raise ValueError(
            f"Unsupported broker type: '{broker_type}'. Supported brokers: {SUPPORTED_BROKERS}"
        )
