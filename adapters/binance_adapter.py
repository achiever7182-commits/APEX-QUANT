"""
adapters/binance_adapter.py

Talks to Binance's TESTNET (fake money, real market data) via ccxt.
This is the pattern you'll repeat for other exchanges/brokers later --
same interface (fetch_candles, place_order), different implementation underneath.

Get free testnet API keys at: https://testnet.binance.vision/
"""

import time
import ccxt
from core.strategy import MarketData


class BinanceTestnetAdapter:
    def __init__(self, api_key: str, api_secret: str, symbol: str = "BTC/USDT"):
        self.symbol = symbol
        self.exchange = ccxt.binance({
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
            "timeout": 15000,
            "options": {"defaultType": "spot", "fetchMarkets": ["spot"]},
        })
        self.exchange.set_sandbox_mode(True)  # <-- testnet, not real money

    def fetch_balance(self, asset: str = "USDT", retries: int = 3) -> float:
        for attempt in range(retries):
            try:
                balance = self.exchange.fetch_balance()
                return float(balance.get(asset, {}).get("free", 0.0))
            except Exception as e:
                if attempt == retries - 1:
                    print(f"[binance_adapter] fetch_balance failed ({e})")
                    return 0.0
                time.sleep(1.0)
        return 0.0

    def fetch_candles(self, timeframe: str = "1m", limit: int = 100, retries: int = 3) -> list[MarketData]:
        for attempt in range(retries):
            try:
                raw = self.exchange.fetch_ohlcv(self.symbol, timeframe=timeframe, limit=limit)
                return [
                    MarketData(
                        symbol=self.symbol,
                        timestamp=int(row[0]),
                        open=float(row[1]),
                        high=float(row[2]),
                        low=float(row[3]),
                        close=float(row[4]),
                        volume=float(row[5]),
                    )
                    for row in raw if len(row) >= 6
                ]
            except Exception as e:
                if attempt == retries - 1:
                    print(f"[binance_adapter] fetch_candles failed ({e})")
                    return []
                time.sleep(1.0)
        return []

    def place_market_order(self, side: str, amount: float, retries: int = 2) -> dict:
        """Place a market order with retry on transient network errors. side = 'buy' or 'sell'."""
        for attempt in range(retries):
            try:
                return self.exchange.create_order(
                    symbol=self.symbol,
                    type="market",
                    side=side,
                    amount=amount,
                )
            except ccxt.InsufficientFunds as e:
                print(f"[binance_adapter] Insufficient funds for {side} order: {e}")
                raise
            except Exception as e:
                if attempt == retries - 1:
                    print(f"[binance_adapter] place_market_order ({side}) failed: {e}")
                    raise
                time.sleep(1.0)

    def place_limit_order(self, side: str, amount: float, price: float, retries: int = 2) -> dict:
        """Place a limit order at the given price. side = 'buy' or 'sell'."""
        for attempt in range(retries):
            try:
                return self.exchange.create_order(
                    symbol=self.symbol,
                    type="limit",
                    side=side,
                    amount=amount,
                    price=price,
                )
            except Exception as e:
                if attempt == retries - 1:
                    print(f"[binance_adapter] place_limit_order ({side}) failed: {e}")
                    raise
                time.sleep(1.0)

    def cancel_order(self, order_id: str) -> dict:
        """Cancel an open limit order by ID."""
        try:
            return self.exchange.cancel_order(order_id, self.symbol)
        except Exception as e:
            print(f"[binance_adapter] cancel_order failed for #{order_id}: {e}")
            return {"id": order_id, "status": "canceled_or_failed"}

    def fetch_order(self, order_id: str) -> dict:
        """Fetch the current status of an order by ID."""
        try:
            return self.exchange.fetch_order(order_id, self.symbol)
        except Exception as e:
            print(f"[binance_adapter] fetch_order failed for #{order_id}: {e}")
            return {"id": order_id, "status": "unknown"}

    def fetch_open_orders(self) -> list[dict]:
        """Return all currently open orders for this symbol."""
        try:
            return self.exchange.fetch_open_orders(self.symbol)
        except Exception as e:
            print(f"[binance_adapter] fetch_open_orders failed: {e}")
            return []

    def get_current_price(self, retries: int = 3) -> float:
        for attempt in range(retries):
            try:
                ticker = self.exchange.fetch_ticker(self.symbol)
                price = float(ticker.get("last") or ticker.get("close") or 0.0)
                if price > 0:
                    return price
            except Exception as e:
                if attempt == retries - 1:
                    print(f"[binance_adapter] get_current_price failed ({e})")
                    return 0.0
                time.sleep(1.0)
        return 0.0

    def get_fee_rate(self) -> dict:
        """Return maker/taker fee rates for this symbol."""
        try:
            fees = self.exchange.fetch_trading_fee(self.symbol)
            return {"maker": fees.get("maker", 0.001), "taker": fees.get("taker", 0.001)}
        except Exception:
            return {"maker": 0.001, "taker": 0.001}

    def get_min_notional(self) -> float:
        """Return the minimum order value (notional) in quote currency for this symbol."""
        try:
            market = self.exchange.market(self.symbol) if self.exchange.markets else self.exchange.load_markets().get(self.symbol)
            if market:
                cost_min = market.get("limits", {}).get("cost", {}).get("min")
                if cost_min is not None and float(cost_min) > 0:
                    return float(cost_min)
                for f in market.get("info", {}).get("filters", []):
                    if f.get("filterType") in ("NOTIONAL", "MIN_NOTIONAL"):
                        val = f.get("minNotional") or f.get("notional")
                        if val is not None and float(val) > 0:
                            return float(val)
        except Exception:
            pass
        return 10.0  # Safe default if network or exchange info unavailable

    def fetch_order_history(self, limit: int = 20) -> list[dict]:
        """Fetch recent order history from Binance testnet for cross-checking."""
        try:
            return self.exchange.fetch_orders(self.symbol, limit=limit)
        except Exception as e:
            print(f"[adapter] Warning: fetch_orders failed ({e})")
            return []

