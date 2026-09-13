"""
adapters/binance_websocket_adapter.py

Unlike binance_adapter.py (which ASKS the exchange for a price every X seconds),
this connects via WebSocket -- the exchange PUSHES every trade tick to us the
instant it happens. This is genuine real-time data, no polling delay.

Order placement still goes through the normal REST API (binance_adapter.py),
because that's how exchanges work -- you receive data via WebSocket, but you
still submit orders via a regular API call.
"""

import json
import threading
import websocket


class BinanceWebSocketAdapter:
    def __init__(self, symbol: str = "btcusdt"):
        self.symbol = symbol.lower()
        self.url = f"wss://stream.testnet.binance.vision/ws/{self.symbol}@trade"
        self.ws = None
        self.on_tick_callback = None
        self._stop_event = threading.Event()
        self._thread = None

    def _on_message(self, ws, message):
        data = json.loads(message)
        # Binance @trade stream fields: 'p' = price, 'T' = trade time (ms), 'q' = quantity
        tick = {
            "price": float(data["p"]),
            "timestamp": int(data["T"]),
            "quantity": float(data["q"]),
        }
        if self.on_tick_callback:
            self.on_tick_callback(tick)

    def _on_error(self, ws, error):
        print(f"WebSocket error: {error}")

    def _on_close(self, ws, close_status_code, close_msg):
        print("WebSocket connection closed.")

    def _run(self):
        while not self._stop_event.is_set():
            try:
                self.ws = websocket.WebSocketApp(
                    self.url,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                )
                self.ws.run_forever(ping_interval=20, ping_timeout=10)
            except Exception as error:
                print(f"WebSocket runner exception: {error}")
            if not self._stop_event.is_set():
                print("WebSocket disconnected. Reconnecting in 3 seconds...")
                self._stop_event.wait(3.0)

    def start(self, on_tick):
        """
        on_tick: a function that takes one argument (the tick dict) and is
        called every single time a new trade happens on the exchange.
        Runs in a background thread so it doesn't block the rest of your code.
        """
        self.on_tick_callback = on_tick
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="websocket-adapter-thread",
        )
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self.ws:
            self.ws.close()

