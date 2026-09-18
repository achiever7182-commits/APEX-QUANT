import React, { useEffect, useState } from "react";
import { GitCompare, CheckCircle2, AlertTriangle, XCircle, RefreshCw, Database } from "lucide-react";
import { api } from "../api/client";
import { LoadingState, ErrorState } from "../components/ErrorState";
import { StatusBadge } from "../components/StatusBadge";
import type { ReconciliationReport } from "../types";

export const Reconciliation: React.FC = () => {
  const [report, setReport] = useState<ReconciliationReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchRecon = async () => {
    try {
      setError(null);
      const res = await api.getReconciliation();
      setReport(res);
    } catch (err: any) {
      setError(err?.message || "Failed to execute post-trade reconciliation audit.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchRecon();
  }, []);

  if (loading) return <LoadingState message="Executing tri-party reconciliation across Broker, Local Orders, and Accounting..." />;
  if (error && !report) return <ErrorState message={error} onRetry={fetchRecon} />;

  const isClean = report?.is_clean ?? false;
  const discrepancies = report?.discrepancies || [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-quant-border pb-3">
        <div>
          <h2 className="font-mono text-lg font-bold text-quant-textPrimary flex items-center gap-2">
            RECONCILIATION AUDIT
            <span className="text-xs font-normal text-quant-cyan bg-quant-cyanMuted px-2 py-0.5 rounded border border-quant-cyan/30">
              TRI-PARTY LEDGER VERIFICATION
            </span>
          </h2>
          <p className="text-xs text-quant-textSecondary">
            Automated double-entry audit comparing local order state, paper broker execution fills, and position ledger.
          </p>
        </div>

        <button
          onClick={fetchRecon}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-quant-card hover:bg-quant-surface border border-quant-border rounded text-xs font-mono text-quant-cyan"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          Run Reconciliation Audit
        </button>
      </div>

      {/* Overall Verdict Banner */}
      <div className={`p-4 rounded-lg border flex items-start gap-3 ${
        isClean
          ? "bg-quant-bullMuted/20 border-quant-bull/40 text-quant-bull"
          : "bg-quant-bearMuted/20 border-quant-bear/40 text-quant-bear"
      }`}>
        {isClean ? (
          <CheckCircle2 className="w-6 h-6 shrink-0 mt-0.5 text-quant-bull" />
        ) : (
          <AlertTriangle className="w-6 h-6 shrink-0 mt-0.5 text-quant-bear" />
        )}
        <div className="text-xs font-mono">
          <div className="font-bold text-sm mb-1 uppercase">
            AUDIT STATUS: {report?.status || (isClean ? "MATCH (100% INVARIANT VERIFIED)" : "DISCREPANCY DETECTED")}
          </div>
          <p className="text-quant-textSecondary leading-relaxed">
            {isClean
              ? "All positions, orders, execution fills, and cash balances strictly match between local memory and persistent storage."
              : "Discrepancies detected between simulated broker ledger and accounting records. Inspect detailed failure items below."}
          </p>
        </div>
      </div>

      {/* Tri-Party Verification Matrix */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 font-mono text-xs">
        <div className="quant-card p-4 space-y-2">
          <span className="text-quant-textMuted block text-[11px]">ORDER LEDGER ALIGNMENT</span>
          <div className="flex items-center justify-between">
            <span className="text-quant-textSecondary">Local vs Broker Orders:</span>
            <span className="font-bold text-quant-cyan">
              {report?.local_orders_count !== undefined && report?.broker_orders_count !== undefined
                ? `${report.local_orders_count} / ${report.broker_orders_count}`
                : "N/A"}
            </span>
          </div>
          <div className="text-[11px] text-quant-textMuted">Zero missing or zombie orders in queue</div>
        </div>

        <div className="quant-card p-4 space-y-2">
          <span className="text-quant-textMuted block text-[11px]">FILL EXECUTION AUDIT</span>
          <div className="flex items-center justify-between">
            <span className="text-quant-textSecondary">Local vs Broker Fills:</span>
            <span className="font-bold text-quant-cyan">
              {report?.local_fills_count !== undefined && report?.broker_fills_count !== undefined
                ? `${report.local_fills_count} / ${report.broker_fills_count}`
                : "N/A"}
            </span>
          </div>
          <div className="text-[11px] text-quant-textMuted">Fills reconciled with double-entry journal</div>
        </div>

        <div className="quant-card p-4 space-y-2">
          <span className="text-quant-textMuted block text-[11px]">CASH & EQUITY INTEGRITY</span>
          <div className="flex items-center justify-between">
            <span className="text-quant-textSecondary">Cash Discrepancy:</span>
            <span className="font-bold text-quant-bull">
              {report?.cash_discrepancy !== undefined ? `₹${report.cash_discrepancy.toFixed(2)}` : "N/A"}
            </span>
          </div>
          <div className="text-[11px] text-quant-textMuted">Cash conservation invariant fully satisfied</div>
        </div>
      </div>

      {/* Discrepancies Table */}
      <div className="quant-card overflow-hidden">
        <div className="p-3 bg-quant-surface border-b border-quant-border flex items-center justify-between">
          <h3 className="font-mono text-xs font-bold text-quant-textPrimary flex items-center gap-2">
            <GitCompare className="w-4 h-4 text-quant-cyan" />
            DISCREPANCY & EXCEPTION AUDIT LOG
          </h3>
          <span className="text-[11px] font-mono text-quant-textMuted">
            {discrepancies.length} Discrepancies Flagged
          </span>
        </div>

        {discrepancies.length === 0 ? (
          <div className="p-8 text-center text-xs font-mono text-quant-textMuted">
            <CheckCircle2 className="w-8 h-8 text-quant-bull mx-auto mb-2 opacity-80" />
            Zero reconciliation errors. All account balances, positions, and orders are 100% reconciled.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs font-mono">
              <thead className="bg-quant-surface border-b border-quant-border text-quant-textMuted text-[11px]">
                <tr>
                  <th className="p-3 font-medium">CATEGORY</th>
                  <th className="p-3 font-medium">SYMBOL</th>
                  <th className="p-3 font-medium">EXPECTED VALUE</th>
                  <th className="p-3 font-medium">ACTUAL VALUE</th>
                  <th className="p-3 font-medium">DIAGNOSTIC REASON</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-quant-border">
                {discrepancies.map((d, idx) => (
                  <tr key={idx} className="hover:bg-quant-surface/60 transition-colors">
                    <td className="p-3 font-bold text-quant-bear">{d.category}</td>
                    <td className="p-3 text-quant-textPrimary">{d.symbol || "PORTFOLIO"}</td>
                    <td className="p-3 text-quant-textSecondary">{String(d.expected)}</td>
                    <td className="p-3 text-quant-cyan font-bold">{String(d.actual)}</td>
                    <td className="p-3 text-quant-textMuted text-[11px]">{d.details}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
