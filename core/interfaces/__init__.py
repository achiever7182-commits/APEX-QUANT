"""
core/interfaces — Foundational Interfaces and Contracts for APEX QUANT.

This package defines asset-agnostic, broker-agnostic, and data-source-agnostic contracts
that enable modular evolution from the single-pair crypto bot to the full NIFTY 500 platform.
"""

from core.interfaces.instrument import (
    AssetClass,
    Exchange,
    Instrument,
)
from core.interfaces.market_data import (
    Bar,
    Tick,
    IMarketDataFeed,
)
from core.interfaces.broker import (
    OrderSide,
    OrderType,
    OrderStatus,
    ProductType,
    Order,
    OrderFill,
    Position,
    PortfolioSnapshot,
    IBroker,
)
from core.interfaces.universe import (
    UniverseFilter,
    IUniverseManager,
)

__all__ = [
    "AssetClass",
    "Exchange",
    "Instrument",
    "Bar",
    "Tick",
    "IMarketDataFeed",
    "OrderSide",
    "OrderType",
    "OrderStatus",
    "ProductType",
    "Order",
    "OrderFill",
    "Position",
    "PortfolioSnapshot",
    "IBroker",
    "UniverseFilter",
    "IUniverseManager",
]
