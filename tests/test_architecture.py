"""
tests/test_architecture.py — Architecture & Interface Verification for APEX QUANT Foundation.

Verifies:
  1. Generic interfaces import cleanly
  2. Asset-agnostic Instrument factory methods function
  3. Market data abstractions (Bar, Tick) validate
  4. Execution abstractions (Order, Position, PortfolioSnapshot) compute metrics
  5. Existing Strategy and MarketData contracts remain backward-compatible
"""

import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from core.interfaces import (
    AssetClass,
    Exchange,
    Instrument,
    Bar,
    Tick,
    Order,
    OrderSide,
    OrderType,
    OrderStatus,
    Position,
    PortfolioSnapshot,
    UniverseFilter,
)
from core.strategy import MarketData, Signal


def test_instrument_abstractions():
    """Verify equity and crypto instrument factories."""
    rel = Instrument.nse_stock("RELIANCE", isin="INE002A01018")
    assert rel.symbol == "RELIANCE"
    assert rel.asset_class == AssetClass.EQUITY
    assert rel.exchange == Exchange.NSE
    assert rel.currency == "INR"
    assert rel.lot_size == 1.0

    btc = Instrument.crypto_pair("BTC/USDT")
    assert btc.symbol == "BTC/USDT"
    assert btc.asset_class == AssetClass.CRYPTO
    assert btc.currency == "USDT"
    print("  [OK] test_instrument_abstractions")


def test_market_data_abstractions():
    """Verify Bar and Tick structures."""
    bar = Bar(
        symbol="TCS",
        timestamp=1700000000000,
        open=3800.0,
        high=3850.0,
        low=3790.0,
        close=3840.0,
        volume=120000.0,
        turnover=460800000.0,
    )
    assert bar.is_bullish is True
    assert bar.turnover > 0

    tick = Tick(symbol="INFY", price=1520.50, quantity=50, timestamp=1700000001000)
    assert tick.price == 1520.50
    print("  [OK] test_market_data_abstractions")


def test_portfolio_and_position():
    """Verify multi-asset Position and PortfolioSnapshot tracking."""
    inst = Instrument.nse_stock("HDFCBANK")
    pos = Position(
        instrument=inst,
        quantity=100.0,
        entry_price=1600.0,
        current_price=1650.0,
        unrealized_pnl=5000.0,
    )
    assert pos.market_value == 165000.0
    assert pos.cost_basis == 160000.0
    assert round(pos.return_pct, 4) == 0.0312

    portfolio = PortfolioSnapshot(
        cash=500000.0,
        equity=665000.0,
        positions={"HDFCBANK": pos},
    )
    assert portfolio.open_position_count == 1
    print("  [OK] test_portfolio_and_position")


def test_backward_compatibility():
    """Verify legacy crypto Strategy MarketData and Signal remain intact."""
    md = MarketData(
        symbol="BTC/USDT",
        timestamp=1700000000000,
        open=75000.0,
        high=75200.0,
        low=74900.0,
        close=75150.0,
        volume=12.5,
    )
    assert md.symbol == "BTC/USDT"
    assert Signal.BUY.value == "BUY"
    assert Signal.HOLD.value == "HOLD"
    print("  [OK] test_backward_compatibility")


if __name__ == "__main__":
    print("Running APEX QUANT Foundation Architecture Tests...")
    test_instrument_abstractions()
    test_market_data_abstractions()
    test_portfolio_and_position()
    test_backward_compatibility()
    print("\nAll Architecture Foundation tests PASSED successfully.")
