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
        try:
            data = json.loads(message)
            if not isinstance(data, dict):
                return
            # Verify required Binance @trade stream fields: 'p' (price) and 'T' (trade time ms)
            if "p" not in data or "T" not in data:
                return
            tick = {
                "price": float(data["p"]),
                "timestamp": int(data["T"]),
                "quantity": float(data.get("q", 0.0)),
            }
            if self.on_tick_callback:
                try:
                    self.on_tick_callback(tick)
                except Exception as cb_err:
                    print(f"[websocket] Warning: error in on_tick callback: {cb_err}")
        except (json.JSONDecodeError, ValueError, TypeError) as parse_err:
            # Silently ignore malformed non-JSON frames or heartbeats
            pass
        except Exception as unhandled:
            print(f"[websocket] Unexpected message error: {unhandled}")

    def _on_error(self, ws, error):
        print(f"[websocket] Stream error: {error}")

    def _on_close(self, ws, close_status_code, close_msg):
        print(f"[websocket] Connection closed (code={close_status_code}, msg={close_msg})")

    def _run(self):
        backoff_seconds = 2.0
        max_backoff = 30.0
        while not self._stop_event.is_set():
            try:
                self.ws = websocket.WebSocketApp(
                    self.url,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                )
                self.ws.run_forever(ping_interval=20, ping_timeout=10)
                backoff_seconds = 2.0  # reset on clean run
            except Exception as error:
                print(f"[websocket] Runner exception: {error}")
            if not self._stop_event.is_set():
                print(f"[websocket] Disconnected. Reconnecting in {backoff_seconds:.1f}s...")
                self._stop_event.wait(backoff_seconds)
                backoff_seconds = min(backoff_seconds * 1.5, max_backoff)

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

