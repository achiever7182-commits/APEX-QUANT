"""
adapters/binance_adapter.py

Talks to Binance's TESTNET (fake money, real market data) via ccxt.
This is the pattern you'll repeat for other exchanges/brokers later --
same interface (fetch_candles, place_order), different implementation underneath.

Get free testnet API keys at: https://testnet.binance.vision/
"""

import ccxt
from core.strategy import MarketData


class BinanceTestnetAdapter:
    def __init__(self, api_key: str, api_secret: str, symbol: str = "BTC/USDT"):
        self.symbol = symbol
        self.exchange = ccxt.binance({
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
        })
        self.exchange.set_sandbox_mode(True)  # <-- testnet, not real money

    def fetch_balance(self, asset: str = "USDT") -> float:
        balance = self.exchange.fetch_balance()
        return balance.get(asset, {}).get("free", 0.0)

    def fetch_candles(self, timeframe: str = "1m", limit: int = 100) -> list[MarketData]:
        raw = self.exchange.fetch_ohlcv(self.symbol, timeframe=timeframe, limit=limit)
        return [
            MarketData(
                symbol=self.symbol,
                timestamp=row[0],
                open=row[1],
                high=row[2],
                low=row[3],
                close=row[4],
                volume=row[5],
            )
            for row in raw
        ]

    def place_market_order(self, side: str, amount: float) -> dict:
        """Place a market order. side = 'buy' or 'sell'."""
        return self.exchange.create_order(
            symbol=self.symbol,
            type="market",
            side=side,
            amount=amount,
        )

    def place_limit_order(self, side: str, amount: float, price: float) -> dict:
        """Place a limit order at the given price. side = 'buy' or 'sell'."""
        return self.exchange.create_order(
            symbol=self.symbol,
            type="limit",
            side=side,
            amount=amount,
            price=price,
        )

    def cancel_order(self, order_id: str) -> dict:
        """Cancel an open limit order by ID."""
        return self.exchange.cancel_order(order_id, self.symbol)

    def fetch_order(self, order_id: str) -> dict:
        """Fetch the current status of an order by ID."""
        return self.exchange.fetch_order(order_id, self.symbol)

    def fetch_open_orders(self) -> list[dict]:
        """Return all currently open orders for this symbol."""
        return self.exchange.fetch_open_orders(self.symbol)

    def get_current_price(self) -> float:
        ticker = self.exchange.fetch_ticker(self.symbol)
        return ticker["last"]

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

