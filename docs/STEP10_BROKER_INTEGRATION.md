# APEX QUANT — STEP 10: BROKER INTEGRATION ARCHITECTURE

## 1. Overview & Objective

Step 10 establishes a production-grade, broker-neutral execution abstraction for Indian equities within APEX QUANT. The primary goal is to cleanly decouple quantitative alpha generation, ranking, and risk control from broker-specific protocols while introducing:
- A standardized **Broker ABC** capability matrix.
- Normalized **Order Translation** converting internal signals into exchange-compliant payloads (e.g., Zerodha Kite Connect).
- **Fail-Closed Execution & Lifecycle Safety**: unambiguous handling of timeouts, socket breaks, and unexpected broker states without blind retries or double-submission risks.
- **Cross-System Reconciliation**: auditing broker positions, fills, and cash against local books without silent state mutations.
- **Strict Live Trading Boundaries**: active safeguards preventing accidental real-world order submission (`LiveTradingDisabledError`).

```
Quantitative Strategy Pipeline:
Market Data → Features → Walk-Forward ML → Ranking → Portfolio Construction → Risk Engine
                                                                                   ↓
                                                                           Order Manager
                                                                                   ↓
                                                                        Broker Interface (ABC)
                                                                       /                      \
                                                        PaperBroker (Simulated)       KiteBrokerAdapter (Safe Stub)
```

---

## 2. Broker Interface Contract (`execution/broker.py`)

The `Broker` abstract base class defines the standard protocol implemented by all simulated and external execution venues:

| Method | Signature | Description |
| :--- | :--- | :--- |
| `submit_order` | `(order: PaperOrder) -> PaperOrder` | Submit an order for validation and routing. |
| `cancel_order` | `(order_id: str) -> bool` | Cancel an in-flight or open order. |
| `get_order` | `(order_id: str) -> Optional[PaperOrder]` | Query order state by unique order ID. |
| `get_orders` | `(status: Optional[OrderStatus] = None) -> List[PaperOrder]` | Retrieve order book, optionally filtered by lifecycle status. |
| `get_positions` | `() -> Dict[str, PaperPosition]` | Query current open positions mapped by symbol. |
| `get_account` | `() -> PaperAccount` | Query cash balance, equity, and margin telemetry. |
| `get_fills` | `(order_id: Optional[str] = None) -> List[PaperFill]` | Retrieve execution fills ledger. |
| `get_quote` | `(symbol: str) -> Optional[float]` | Query latest market quote. |
| `reconcile` | `() -> Dict[str, Any]` | Internal ledger consistency audit. |
| `get_capabilities`| `() -> BrokerCapabilities` | Return capability matrix for the venue. |
| `get_connection_status` | `() -> BrokerConnectionState` | Return connection health status. |

---

## 3. Capability Matrix Model (`execution/models.py`)

Different brokers support distinct features (order types, fractional shares, shorting). The `BrokerCapabilities` dataclass makes these explicit:

```python
@dataclass
class BrokerCapabilities:
    supports_market_orders: bool = True
    supports_limit_orders: bool = True
    supports_stop_orders: bool = False
    supports_order_cancellation: bool = True
    supports_order_status_query: bool = True
    supports_positions_query: bool = True
    supports_account_balance_query: bool = True
    supports_fills_query: bool = True
    supports_integer_shares: bool = True
    supports_fractional_shares: bool = False
    supports_shorting: bool = False
    supports_live_orders: bool = False  # Strictly False in Step 10
    broker_name: str = "AbstractBroker"
    supported_exchanges: List[str] = field(default_factory=lambda: ["NSE"])
```

### Current Implementations:
- **`PaperBroker`**: Full simulation, integer shares, long-only, zero live execution.
- **`KiteBrokerAdapter`**: Zerodha Kite Connect v3 stub, `supports_live_orders=False`, exchanges `["NSE", "BSE"]`.

---

## 4. Order Translation Layer (`execution/order_translator.py`)

Decouples internal `PaperOrder` representations from vendor-specific payload specifications.

### Broker-Neutral Request (`BrokerOrderRequest`)
- `symbol`, `exchange` (default `"NSE"`), `side` (`BUY`/`SELL`), `order_type` (`MARKET`/`LIMIT`), `quantity` (int), `product` (`"CNC"`), `validity` (`"DAY"`), `limit_price`, `tag`, `client_order_id`.

### Zerodha Kite Connect Mapping
Converts internal order requests to standard Kite Connect v3 POST parameters:
```json
{
  "variety": "regular",
  "exchange": "NSE",
  "tradingsymbol": "RELIANCE",
  "transaction_type": "BUY",
  "quantity": 50,
  "product": "CNC",
  "order_type": "LIMIT",
  "validity": "DAY",
  "price": 2850.50,
  "tag": "ORD12345"
}
```

---

## 5. Fail-Closed Execution Safety (`execution/order_manager.py`)

In institutional algorithmic trading, **network ambiguity is risk**. If an API request times out or returns an HTTP 504:
1. **Never blind retry**: Retrying an order whose state is unknown can result in duplicate fills and catastrophic double-exposure.
2. **Mark as `SUBMITTED` / `UNCERTAIN`**: Order remains in `active_orders` registry.
3. **Trigger reconciliation**: Order state must be resolved by querying the broker or through webhook audit before subsequent orders on that symbol are permitted.

Implemented in `OrderManager.submit_order`:
- Catches `BrokerTimeoutError` and `BrokerUncertainStateError`.
- Transitions `order.status = OrderStatus.SUBMITTED` with `order.metadata["uncertain_state"] = True`.
- Emits high-priority `ORDER_TIMEOUT_UNCERTAIN` audit event.

---

## 6. Broker Factory & Live Safety Gate (`execution/broker_factory.py`)

Factory function `create_broker(broker_type, trading_mode, **kwargs)` enforces fail-closed validation:
- If `trading_mode == "live"`: unconditionally raises `LiveTradingDisabledError`.
- Only allows simulated or stub execution in Step 10.

---

## 7. Cross-System Reconciliation (`execution/reconciliation.py`)

`ReconciliationEngine.reconcile_with_broker` compares internal books against external broker responses:
1. **Cash Balance Audit**: Verifies `local_account.cash == broker_account.cash`.
2. **Position Quantity Audit**: Audits share counts symbol-by-symbol; flags `BROKER_POSITION_MISMATCH`.
3. **Orphan Order Audit**: Detects any orders resting on the broker that do not exist locally (`BROKER_ORDER_ORPHAN`).
4. **Order Status Alignment**: Detects discrepancies between local order statuses and broker order statuses.
5. **Zero Silent Mutations**: Any mismatch generates a structured `ReconciliationReport` without overwriting ledger state.
