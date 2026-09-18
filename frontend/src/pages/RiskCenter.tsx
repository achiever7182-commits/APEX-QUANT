import React, { useEffect, useState } from "react";
import { ShieldCheck, ShieldAlert, Power, AlertTriangle, CheckCircle2, XCircle, Clock, Info } from "lucide-react";
import { api } from "../api/client";
import { LoadingState, ErrorState } from "../components/ErrorState";
import { StatusBadge } from "../components/StatusBadge";
import { MetricCard } from "../components/MetricCard";
import type { RiskStatus } from "../types";

interface RiskCenterProps {
  onOpenKillSwitchModal: () => void;
}

export const RiskCenter: React.FC<RiskCenterProps> = ({ onOpenKillSwitchModal }) => {
  const [risk, setRisk] = useState<RiskStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchRisk = async () => {
    try {
      setError(null);
      const res = await api.getRiskStatus();
      setRisk(res);
    } catch (err: any) {
      setError(err?.message || "Failed to query 12-point pre-trade risk engine.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchRisk();
    const interval = setInterval(fetchRisk, 5000); // 5s refresh
    return () => clearInterval(interval);
  }, []);

  if (loading) return <LoadingState message="Evaluating 12 pre-trade risk checks against paper ledger..." />;
  if (error && !risk) return <ErrorState message={error} onRetry={fetchRisk} />;

  const u = risk?.utilization;
  const limits = risk?.limits;
  const isKillSwitchActive = risk?.kill_switch?.active ?? false;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-quant-border pb-3">
        <div>
          <h2 className="font-mono text-lg font-bold text-quant-textPrimary flex items-center gap-2">
            RISK CENTER
            <span className="text-xs font-normal text-quant-cyan bg-quant-cyanMuted px-2 py-0.5 rounded border border-quant-cyan/30">
              12-POINT PRE-TRADE SAFETY ENGINE
            </span>
          </h2>
          <p className="text-xs text-quant-textSecondary">
            Hard circuit breakers, single-stock and sector concentration caps, and persistent order kill-switch.
          </p>
        </div>

        {/* Prominent Kill Switch Trigger */}
        <button
          onClick={onOpenKillSwitchModal}
          className={`px-4 py-2 rounded-lg font-mono text-xs font-bold border transition-all flex items-center gap-2 shadow-lg ${
            isKillSwitchActive
              ? "bg-quant-bear hover:bg-quant-bear/90 text-white border-quant-bear animate-pulse"
              : "bg-quant-card hover:bg-quant-surface text-quant-warn border-quant-warn/50 hover:border-quant-warn"
          }`}
        >
          <Power className="w-4 h-4" />
          <span>{isKillSwitchActive ? "KILL SWITCH ENGAGED (ORDERS HALTED)" : "KILL SWITCH: ARMED & READY"}</span>
        </button>
      </div>

      {/* Top Utilization Gauges */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3.5">
        <MetricCard
          title="DAILY LOSS UTILIZATION"
          value={
            u?.daily_loss_pct !== undefined && limits?.max_daily_loss_pct !== undefined
              ? `${u.daily_loss_pct.toFixed(2)}% / ${limits.max_daily_loss_pct.toFixed(2)}%`
              : "N/A"
          }
          subtitle={
            u?.daily_loss_pct !== undefined && limits?.max_daily_loss_pct !== undefined && u.daily_loss_pct > (limits.max_daily_loss_pct * 0.67)
              ? "Approaching Limit"
              : "Safe Zone"
          }
          tooltip="Intraday equity drawdown circuit breaker. Trading halts if daily loss reaches configured limit."
          accentColor={
            u?.daily_loss_pct !== undefined && limits?.max_daily_loss_pct !== undefined && u.daily_loss_pct > (limits.max_daily_loss_pct * 0.67)
              ? "warn"
              : "default"
          }
        />

        <MetricCard
          title="MAX DRAWDOWN"
          value={
            u?.drawdown_pct !== undefined && limits?.max_drawdown_pct !== undefined
              ? `${u.drawdown_pct.toFixed(2)}% / ${limits.max_drawdown_pct.toFixed(2)}%`
              : "N/A"
          }
          subtitle="Peak-to-Trough Cap"
          tooltip="Hard stop limit ensuring paper equity cannot decline by more than limit from high watermark."
          accentColor={
            u?.drawdown_pct !== undefined && limits?.max_drawdown_pct !== undefined && u.drawdown_pct > (limits.max_drawdown_pct * 0.7)
              ? "warn"
              : "default"
          }
        />

        <MetricCard
          title="SINGLE-STOCK CAP"
          value={
            u?.max_stock_concentration_pct !== undefined && limits?.max_single_stock_weight_pct !== undefined
              ? `${u.max_stock_concentration_pct.toFixed(1)}% / ${limits.max_single_stock_weight_pct.toFixed(1)}%`
              : "N/A"
          }
          subtitle={`Max: ${u?.max_stock_symbol || "NONE"}`}
          tooltip="Maximum allowed allocation in any individual equity. Orders exceeding limit are rejected."
          accentColor={
            u?.max_stock_concentration_pct !== undefined && limits?.max_single_stock_weight_pct !== undefined && u.max_stock_concentration_pct > (limits.max_single_stock_weight_pct * 0.85)
              ? "warn"
              : "default"
          }
        />

        <MetricCard
          title="SECTOR EXPOSURE CAP"
          value={
            u?.max_sector_concentration_pct !== undefined && limits?.max_sector_weight_pct !== undefined
              ? `${u.max_sector_concentration_pct.toFixed(1)}% / ${limits.max_sector_weight_pct.toFixed(1)}%`
              : "N/A"
          }
          subtitle={`Max: ${u?.max_sector_name || "NONE"}`}
          tooltip="Maximum allowed allocation within a single macro sector."
          accentColor={
            u?.max_sector_concentration_pct !== undefined && limits?.max_sector_weight_pct !== undefined && u.max_sector_concentration_pct > (limits.max_sector_weight_pct * 0.8)
              ? "warn"
              : "default"
          }
        />
      </div>

      {/* 12-Point Checks Table */}
      <div className="quant-card overflow-hidden">
        <div className="p-3 bg-quant-surface border-b border-quant-border flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-quant-cyan" />
            <h3 className="font-mono text-xs font-bold text-quant-textPrimary">
              12-POINT PRE-TRADE SAFETY CHECKLIST (EVALUATED PER ORDER)
            </h3>
          </div>
          <StatusBadge status={risk?.overall_status || "HEALTHY"} size="sm" />
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs font-mono">
            <thead className="bg-quant-surface border-b border-quant-border text-quant-textMuted text-[11px]">
              <tr>
                <th className="p-3 font-medium">#</th>
                <th className="p-3 font-medium">SAFETY CHECK NAME</th>
                <th className="p-3 font-medium text-center">STATUS</th>
                <th className="p-3 font-medium">OBSERVED VALUE</th>
                <th className="p-3 font-medium">CONFIGURED LIMIT</th>
                <th className="p-3 font-medium">PROTECTION DETAILS</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-quant-border">
              {(risk?.checks || []).map((chk) => (
                <tr key={chk.id} className="hover:bg-quant-surface/60 transition-colors">
                  <td className="p-3 text-quant-textMuted font-bold">
                    {chk.id.toString().padStart(2, "0")}
                  </td>

                  <td className="p-3 font-bold text-quant-textPrimary">
                    {chk.name}
                  </td>

                  <td className="p-3 text-center">
                    <StatusBadge status={chk.status} size="sm" />
                  </td>

                  <td className="p-3 text-quant-cyan font-bold">
                    {chk.current}
                  </td>

                  <td className="p-3 text-quant-textSecondary">
                    {chk.limit}
                  </td>

                  <td className="p-3 text-quant-textMuted text-[11px]">
                    {chk.details}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
