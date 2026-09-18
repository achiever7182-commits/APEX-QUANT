import React, { useEffect, useState } from "react";
import { ListOrdered, Filter, CheckCircle2, XCircle, Clock, ChevronRight, X, ShieldAlert, ArrowRight } from "lucide-react";
import { api } from "../api/client";
import { LoadingState, ErrorState, EmptyState } from "../components/ErrorState";
import { StatusBadge } from "../components/StatusBadge";
import type { Order, Fill } from "../types";

export const Orders: React.FC = () => {
  const [orders, setOrders] = useState<Order[]>([]);
  const [fills, setFills] = useState<Fill[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedOrder, setSelectedOrder] = useState<Order | null>(null);

  // Filters
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [sideFilter, setSideFilter] = useState<string>("ALL");

  const fetchOrders = async () => {
    try {
      setError(null);
      const [ordRes, fillRes] = await Promise.all([
        api.getOrders(),
        api.getFills(),
      ]);
      // Sort orders descending by created_at
      const sorted = (ordRes || []).sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
      setOrders(sorted);
      setFills(fillRes || []);
    } catch (err: any) {
      setError(err?.message || "Failed to load orders ledger.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchOrders();
    const interval = setInterval(fetchOrders, 10000);
    return () => clearInterval(interval);
  }, []);

  if (loading) return <LoadingState message="Querying paper order ledger & fill audit trail..." />;
  if (error && orders.length === 0) return <ErrorState message={error} onRetry={fetchOrders} />;

  // Map order_id to fill data for fees & slippage
  const fillMap: Record<string, Fill> = {};
  fills.forEach((f) => {
    fillMap[f.order_id] = f;
  });

  const filtered = orders.filter((o) => {
    const matchStatus = statusFilter === "ALL" || o.status === statusFilter;
    const matchSide = sideFilter === "ALL" || o.side === sideFilter;
    return matchStatus && matchSide;
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-quant-border pb-3">
        <div>
          <h2 className="font-mono text-lg font-bold text-quant-textPrimary flex items-center gap-2">
            PAPER ORDERS LEDGER
            <span className="text-xs font-normal text-quant-cyan bg-quant-cyanMuted px-2 py-0.5 rounded border border-quant-cyan/30">
              AUDIT TRAIL
            </span>
          </h2>
          <p className="text-xs text-quant-textSecondary">
            Execution lifecycle, pre-trade risk decisions, fills, and cost accounting.
          </p>
        </div>

        <div className="flex items-center gap-2 text-xs font-mono text-quant-textMuted">
          <span>Total Recorded:</span>
          <span className="text-quant-textPrimary font-semibold">{orders.length} orders</span>
          <span className="text-quant-borderBright">|</span>
          <span>Fills:</span>
          <span className="text-quant-bull font-semibold">{fills.length} executed</span>
        </div>
      </div>

      {/* Filter Bar */}
      <div className="quant-card p-3 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-1.5 text-xs font-mono">
            <span className="text-quant-textMuted">STATUS:</span>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="bg-quant-surface border border-quant-border rounded px-2.5 py-1 text-xs font-mono text-quant-textPrimary focus:outline-none focus:border-quant-cyan"
            >
              <option value="ALL">ALL STATUSES</option>
              <option value="FILLED">FILLED</option>
              <option value="REJECTED">REJECTED</option>
              <option value="SUBMITTED">SUBMITTED</option>
              <option value="PENDING">PENDING</option>
              <option value="CANCELLED">CANCELLED</option>
            </select>
          </div>

          <div className="flex items-center gap-1.5 text-xs font-mono">
            <span className="text-quant-textMuted">SIDE:</span>
            <select
              value={sideFilter}
              onChange={(e) => setSideFilter(e.target.value)}
              className="bg-quant-surface border border-quant-border rounded px-2.5 py-1 text-xs font-mono text-quant-textPrimary focus:outline-none focus:border-quant-cyan"
            >
              <option value="ALL">ALL SIDES</option>
              <option value="BUY">BUY ONLY</option>
              <option value="SELL">SELL ONLY</option>
            </select>
          </div>
        </div>

        <span className="text-[11px] font-mono text-quant-textMuted">
          Click any order row to inspect full lifecycle audit trail
        </span>
      </div>

      {/* Orders Table */}
      <div className="quant-card overflow-hidden">
        {filtered.length === 0 ? (
          <EmptyState message="No orders found matching the filter criteria." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs font-mono">
              <thead className="bg-quant-surface border-b border-quant-border text-quant-textMuted text-[11px]">
                <tr>
                  <th className="p-3 font-medium">TIME (UTC)</th>
                  <th className="p-3 font-medium">ORDER ID</th>
                  <th className="p-3 font-medium">SYMBOL</th>
                  <th className="p-3 font-medium">SIDE</th>
                  <th className="p-3 font-medium">TYPE</th>
                  <th className="p-3 font-medium text-right">QUANTITY</th>
                  <th className="p-3 font-medium text-right">FILL PRICE</th>
                  <th className="p-3 font-medium text-center">STATUS</th>
                  <th className="p-3 font-medium text-right">FEES (10bps)</th>
                  <th className="p-3 font-medium text-right">SLIPPAGE (5bps)</th>
                  <th className="p-3 font-medium text-right"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-quant-border">
                {filtered.map((order) => {
                  const fill = fillMap[order.order_id];
                  const isBuy = order.side === "BUY";
                  const timeStr = order.created_at ? order.created_at.slice(0, 19).replace("T", " ") : "—";

                  return (
                    <tr
                      key={order.order_id}
                      onClick={() => setSelectedOrder(order)}
                      className="hover:bg-quant-surface/60 cursor-pointer transition-colors group"
                    >
                      <td className="p-3 text-quant-textMuted text-[11px]">
                        {timeStr}
                      </td>

                      <td className="p-3 font-bold text-quant-textSecondary group-hover:text-quant-cyan">
                        {order.order_id}
                      </td>

                      <td className="p-3 font-bold text-quant-textPrimary">
                        {order.symbol}
                      </td>

                      <td className="p-3">
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                            isBuy
                              ? "bg-quant-bullMuted text-quant-bull border border-quant-bull/30"
                              : "bg-quant-bearMuted text-quant-bear border border-quant-bear/30"
                          }`}
                        >
                          {order.side}
                        </span>
                      </td>

                      <td className="p-3 text-quant-textMuted">
                        {order.order_type}
                      </td>

                      <td className="p-3 text-right font-medium text-quant-textPrimary">
                        {order.filled_quantity} / {order.requested_quantity}
                      </td>

                      <td className="p-3 text-right font-medium text-quant-textPrimary">
                        {order.average_fill_price ? `₹${order.average_fill_price.toFixed(2)}` : "—"}
                      </td>

                      <td className="p-3 text-center">
                        <StatusBadge status={order.status} size="sm" />
                      </td>

                      <td className="p-3 text-right text-quant-textMuted">
                        {fill ? `₹${fill.transaction_fee.toFixed(2)}` : "—"}
                      </td>

                      <td className="p-3 text-right text-quant-textMuted">
                        {fill ? `₹${fill.slippage_cost.toFixed(2)}` : "—"}
                      </td>

                      <td className="p-3 text-right">
                        <ChevronRight className="w-4 h-4 text-quant-textMuted group-hover:text-quant-cyan transition-transform group-hover:translate-x-0.5" />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Order Details Drawer / Modal */}
      {selectedOrder && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
          <div className="bg-quant-surface border border-quant-borderBright w-full max-w-2xl rounded-xl shadow-2xl p-6 relative max-h-[90vh] overflow-y-auto">
            <button
              onClick={() => setSelectedOrder(null)}
              className="absolute top-4 right-4 text-quant-textMuted hover:text-quant-textPrimary"
            >
              <X className="w-5 h-5" />
            </button>

            <div className="flex items-center gap-3 border-b border-quant-border pb-4 mb-4">
              <div className="w-10 h-10 rounded-lg bg-quant-card border border-quant-border flex items-center justify-center font-mono font-bold text-sm text-quant-cyan">
                {selectedOrder.symbol.slice(0, 2)}
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-base font-bold font-mono text-quant-textPrimary">
                    {selectedOrder.symbol} {selectedOrder.side}
                  </h3>
                  <StatusBadge status={selectedOrder.status} size="sm" />
                </div>
                <p className="text-xs font-mono text-quant-textMuted">
                  Order ID: {selectedOrder.order_id}
                </p>
              </div>
            </div>

            {/* Lifecycle Stages */}
            <div className="mb-6">
              <h4 className="text-xs font-mono font-bold text-quant-textSecondary uppercase tracking-wide mb-3">
                EXECUTION PIPELINE LIFECYCLE
              </h4>

              <div className="flex flex-wrap items-center gap-2 text-xs font-mono bg-quant-card p-3 rounded-lg border border-quant-border">
                <span className="text-quant-bull font-bold">1. SIGNAL</span>
                <ArrowRight className="w-3.5 h-3.5 text-quant-textMuted" />
                <span className="text-quant-bull font-bold">2. STAGED</span>
                <ArrowRight className="w-3.5 h-3.5 text-quant-textMuted" />
                <span className={selectedOrder.status === "REJECTED" ? "text-quant-bear font-bold" : "text-quant-bull font-bold"}>
                  3. RISK CHECK
                </span>
                <ArrowRight className="w-3.5 h-3.5 text-quant-textMuted" />
                <span className={selectedOrder.status === "FILLED" ? "text-quant-bull font-bold" : "text-quant-textMuted"}>
                  4. SUBMITTED
                </span>
                <ArrowRight className="w-3.5 h-3.5 text-quant-textMuted" />
                <span className={selectedOrder.status === "FILLED" ? "text-quant-cyan font-bold" : "text-quant-textMuted"}>
                  5. FILLED
                </span>
                <ArrowRight className="w-3.5 h-3.5 text-quant-textMuted" />
                <span className={selectedOrder.status === "FILLED" ? "text-quant-textSecondary font-bold" : "text-quant-textMuted"}>
                  6. ACCOUNTED
                </span>
              </div>
            </div>

            {/* Rejection Diagnostics if rejected */}
            {selectedOrder.status === "REJECTED" && (
              <div className="mb-5 p-3.5 bg-quant-bearMuted border border-quant-bear/40 rounded-lg space-y-1">
                <div className="flex items-center gap-2 text-quant-bear font-bold text-xs font-mono">
                  <ShieldAlert className="w-4 h-4" />
                  REJECTION REASON: {selectedOrder.rejection_reason || "RISK_LIMIT_EXCEEDED"}
                </div>
                <p className="text-xs text-quant-textPrimary leading-relaxed">
                  {selectedOrder.rejection_details || "Order breached pre-trade risk engine limits."}
                </p>
              </div>
            )}

            {/* Details Grid */}
            <div className="grid grid-cols-2 gap-3 text-xs font-mono mb-6">
              <div className="p-2.5 bg-quant-card rounded border border-quant-border">
                <span className="text-quant-textMuted block text-[10px]">REQUESTED QUANTITY</span>
                <span className="font-bold text-quant-textPrimary text-sm">{selectedOrder.requested_quantity} shares</span>
              </div>

              <div className="p-2.5 bg-quant-card rounded border border-quant-border">
                <span className="text-quant-textMuted block text-[10px]">FILLED QUANTITY</span>
                <span className="font-bold text-quant-textPrimary text-sm">{selectedOrder.filled_quantity} shares</span>
              </div>

              <div className="p-2.5 bg-quant-card rounded border border-quant-border">
                <span className="text-quant-textMuted block text-[10px]">AVERAGE FILL PRICE</span>
                <span className="font-bold text-quant-cyan text-sm">
                  {selectedOrder.average_fill_price ? `₹${selectedOrder.average_fill_price.toFixed(2)}` : "—"}
                </span>
              </div>

              <div className="p-2.5 bg-quant-card rounded border border-quant-border">
                <span className="text-quant-textMuted block text-[10px]">IDEMPOTENCY KEY</span>
                <span className="font-bold text-quant-textSecondary text-[11px] truncate block" title={selectedOrder.idempotency_key || ""}>
                  {selectedOrder.idempotency_key || "NONE"}
                </span>
              </div>

              <div className="p-2.5 bg-quant-card rounded border border-quant-border">
                <span className="text-quant-textMuted block text-[10px]">CREATED AT</span>
                <span className="font-medium text-quant-textSecondary">{selectedOrder.created_at}</span>
              </div>

              <div className="p-2.5 bg-quant-card rounded border border-quant-border">
                <span className="text-quant-textMuted block text-[10px]">COMPLETED AT</span>
                <span className="font-medium text-quant-textSecondary">{selectedOrder.completed_at || "—"}</span>
              </div>
            </div>

            <div className="flex justify-end">
              <button
                onClick={() => setSelectedOrder(null)}
                className="px-4 py-2 bg-quant-card hover:bg-quant-elevated text-xs font-mono font-medium text-quant-textPrimary border border-quant-border rounded-lg"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
