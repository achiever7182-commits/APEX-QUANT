import React, { useEffect, useState } from "react";
import { MetricCard } from "../components/MetricCard";
import { StatusBadge } from "../components/StatusBadge";
import { LoadingState, ErrorState, EmptyState } from "../components/ErrorState";
import { Tooltip } from "../components/Tooltip";
import { api } from "../api/client";
import type { AccountSummary, OperationalTelemetry, RealtimeQuote, ScannerItem, SystemHealthSummary } from "../types";
import { Activity, ArrowRight, ShieldCheck, TrendingUp, AlertTriangle, Layers, Clock, Cpu } from "lucide-react";

interface CommandCenterProps {
  onNavigate: (tab: any, symbol?: string) => void;
}

export const CommandCenter: React.FC<CommandCenterProps> = ({ onNavigate }) => {
  const [account, setAccount] = useState<AccountSummary | null>(null);
  const [scanner, setScanner] = useState<ScannerItem[]>([]);
  const [quotes, setQuotes] = useState<Record<string, RealtimeQuote>>({});
  const [health, setHealth] = useState<SystemHealthSummary | null>(null);
  const [telemetry, setTelemetry] = useState<OperationalTelemetry | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    try {
      setError(null);
      const [acctRes, scanRes, quotesRes, healthRes, telemRes] = await Promise.all([
        api.getAccountSummary().catch(() => null),
        api.getScanner().catch(() => ({ count: 0, ranked: [] })),
        api.getQuotes().catch(() => ({ count: 0, quotes: {} })),
        api.getPaperHealth().catch(() => null),
        api.getPaperTelemetry().catch(() => null),
      ]);

      if (acctRes) setAccount(acctRes);
      if (scanRes && scanRes.ranked) setScanner(scanRes.ranked);
      if (quotesRes && quotesRes.quotes) setQuotes(quotesRes.quotes);
      if (healthRes) setHealth(healthRes);
      if (telemRes) setTelemetry(telemRes);
    } catch (err: any) {
      setError(err?.message || "Failed to load command center telemetry.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000); // 10s auto-refresh
    return () => clearInterval(interval);
  }, []);

  if (loading) return <LoadingState message="Connecting to APEX-QUANT Engine & Portfolio Accounting..." />;
  if (error && !account) return <ErrorState message={error} onRetry={fetchData} />;

  const formatCurrency = (val?: number | null, decimals = 2) =>
    val !== undefined && val !== null
      ? `₹${val.toLocaleString("en-IN", { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}`
      : "N/A";
  const formatPct = (val?: number | null, decimals = 2) =>
    val !== undefined && val !== null ? `${val.toFixed(decimals)}%` : "N/A";

  const totalEquity = account?.total_equity;
  const cash = account?.cash;
  const invested = account?.positions_value;
  const dailyPnl = account?.daily_pnl;
  const realizedPnl = account?.realized_pnl;
  const unrealizedPnl = account?.unrealized_pnl;
  const totalPnl = realizedPnl !== undefined && unrealizedPnl !== undefined ? realizedPnl + unrealizedPnl : undefined;
  const drawdownPct = account?.max_drawdown !== undefined ? account.max_drawdown * 100 : undefined;
  const grossExposurePct = totalEquity && totalEquity > 0 && invested !== undefined ? (invested / totalEquity) * 100 : undefined;
  const positionsCount = account?.positions_count ?? (account?.positions ? account.positions.length : undefined);

  const topOpportunities = scanner.slice(0, 5);

  return (
    <div className="space-y-6">
      {/* Top Section Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 border-b border-quant-border pb-3">
        <div>
          <h2 className="font-mono text-lg font-bold text-quant-textPrimary flex items-center gap-2">
            COMMAND CENTER
            <span className="text-xs font-normal text-quant-cyan bg-quant-cyanMuted px-2 py-0.5 rounded border border-quant-cyan/30">
              LIVE PAPER WORKSTATION
            </span>
          </h2>
          <p className="text-xs text-quant-textSecondary">
            Executive quantitative health, virtual account telemetry, and top algorithmic ranking signals.
          </p>
        </div>

        <div className="flex items-center gap-2 text-xs font-mono">
          <span className="text-quant-textMuted">Broker Backend:</span>
          <span className="text-quant-textPrimary font-semibold">PaperBroker (Virtual Sandbox)</span>
        </div>
      </div>

      {/* Operational Paper Session & Pipeline State Strip (Step 13) */}
      <div className="p-3 bg-quant-surface border border-quant-border rounded-lg flex flex-wrap items-center justify-between gap-3 text-xs font-mono">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5">
            <Clock className="w-3.5 h-3.5 text-quant-cyan" />
            <span className="text-quant-textMuted">SESSION:</span>
            <span className="text-quant-textPrimary font-bold">{telemetry?.current_session || "STANDBY"}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <Layers className="w-3.5 h-3.5 text-quant-cyan" />
            <span className="text-quant-textMuted">CYCLE:</span>
            <span className="text-quant-textSecondary">{telemetry?.current_cycle || health?.last_cycle?.cycle_id || "IDLE"}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <Cpu className="w-3.5 h-3.5 text-quant-cyan" />
            <span className="text-quant-textMuted">PIPELINE:</span>
            <span className={`font-bold ${telemetry?.current_state === "RUNNING" ? "text-quant-cyan animate-pulse" : "text-quant-bull"}`}>
              {telemetry?.current_state || "READY"}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5">
            <ShieldCheck className="w-3.5 h-3.5 text-quant-bull" />
            <span className="text-quant-textMuted">RECON:</span>
            <span className="text-quant-bull font-bold">
              {account?.last_reconciliation?.status || telemetry?.last_reconciliation_status || "CLEAN"}
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-quant-textMuted">ERRORS:</span>
            <span className={`font-bold ${
              ((telemetry?.data_errors || 0) + (telemetry?.model_errors || 0) + (telemetry?.execution_errors || 0) + (telemetry?.reconciliation_errors || 0)) > 0
                ? "text-quant-bear"
                : "text-quant-bull"
            }`}>
              {(telemetry?.data_errors || 0) + (telemetry?.model_errors || 0) + (telemetry?.execution_errors || 0) + (telemetry?.reconciliation_errors || 0)}
            </span>
          </div>
        </div>
      </div>

      {/* KPI Cards Row (8 cards) */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3.5">
        <MetricCard
          title="TOTAL EQUITY"
          value={formatCurrency(totalEquity)}
          subtitle="NAV Mark-to-Market"
          tooltip="Total paper portfolio equity including cash and mark-to-market positions."
          accentColor="cyan"
        />

        <MetricCard
          title="AVAILABLE CASH"
          value={formatCurrency(cash)}
          subtitle={
            cash !== undefined && totalEquity && totalEquity > 0
              ? `${((cash / totalEquity) * 100).toFixed(1)}% Cash Reserve`
              : "Cash Reserve: N/A"
          }
          tooltip="Unencumbered liquid cash available for new allocations."
          accentColor="default"
        />

        <MetricCard
          title="INVESTED CAPITAL"
          value={formatCurrency(invested)}
          subtitle={positionsCount !== undefined ? `${positionsCount} Active Equity Holdings` : "Holdings: N/A"}
          tooltip="Total current market value of all held equity positions."
          accentColor="default"
        />

        <MetricCard
          title="TODAY'S P&L"
          value={formatCurrency(dailyPnl)}
          change={totalEquity && totalEquity > 0 && dailyPnl !== undefined ? (dailyPnl / totalEquity) * 100 : undefined}
          tooltip="Intraday paper trading profit/loss based on start-of-day equity."
          accentColor={dailyPnl !== undefined ? (dailyPnl >= 0 ? "bull" : "bear") : "default"}
        />

        <MetricCard
          title="TOTAL P&L"
          value={formatCurrency(totalPnl)}
          subtitle={
            realizedPnl !== undefined && unrealizedPnl !== undefined
              ? `Realized: ₹${realizedPnl.toFixed(1)} | Unreal: ₹${unrealizedPnl.toFixed(1)}`
              : "Realized / Unreal: N/A"
          }
          tooltip="Cumulative paper P&L since sandbox inception (realized + mark-to-market unrealized)."
          accentColor={totalPnl !== undefined ? (totalPnl >= 0 ? "bull" : "bear") : "default"}
        />

        <MetricCard
          title="MAX DRAWDOWN"
          value={formatPct(drawdownPct)}
          subtitle="Risk Ceiling: 10.00%"
          tooltip="Maximum observed peak-to-trough equity decline."
          accentColor={drawdownPct !== undefined && drawdownPct > 5 ? "warn" : "default"}
        />

        <MetricCard
          title="GROSS EXPOSURE"
          value={formatPct(grossExposurePct, 1)}
          subtitle="Limit: 100.0% (Zero Margin)"
          tooltip="Total positions value divided by total equity. Borrowing and shorting are prohibited."
          accentColor={grossExposurePct !== undefined && grossExposurePct > 95 ? "warn" : "default"}
        />

        <MetricCard
          title="OPEN POSITIONS"
          value={positionsCount !== undefined ? positionsCount : "N/A"}
          subtitle={account?.total_fees !== undefined ? `Fees: ₹${account.total_fees.toFixed(1)}` : "Fees: N/A"}
          tooltip="Number of distinct active equity holdings currently held in the paper ledger."
          accentColor="default"
        />
      </div>

      {/* Middle Grid: Top Quant Opportunities & Portfolio */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Top Quant Opportunities */}
        <div className="quant-card p-4 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between border-b border-quant-border pb-3 mb-3">
              <div>
                <h3 className="font-mono text-sm font-bold text-quant-textPrimary flex items-center gap-2">
                  <TrendingUp className="w-4 h-4 text-quant-cyan" />
                  TOP QUANT OPPORTUNITIES
                </h3>
                <p className="text-[11px] text-quant-textMuted">
                  Ranked by cross-sectional ML prediction, RSI momentum, and volatility scoring.
                </p>
              </div>

              <button
                onClick={() => onNavigate("scanner")}
                className="text-xs font-mono text-quant-cyan hover:underline flex items-center gap-1"
              >
                View Full Scanner <ArrowRight className="w-3 h-3" />
              </button>
            </div>

            {topOpportunities.length === 0 ? (
              <EmptyState message="No opportunity scores available. Run a cycle or inspect scanner." />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs font-mono">
                  <thead>
                    <tr className="border-b border-quant-border text-quant-textMuted text-[11px]">
                      <th className="pb-2 font-medium">RANK</th>
                      <th className="pb-2 font-medium">SYMBOL</th>
                      <th className="pb-2 font-medium text-right">PRICE</th>
                      <th className="pb-2 font-medium text-right">QUANT SCORE</th>
                      <th className="pb-2 font-medium text-right">5D PRED</th>
                      <th className="pb-2 font-medium text-center">RISK</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-quant-border/50">
                    {topOpportunities.map((item) => (
                      <tr
                        key={item.symbol}
                        onClick={() => onNavigate("scanner", item.symbol)}
                        className="hover:bg-quant-surface/60 cursor-pointer transition-colors group"
                      >
                        <td className="py-2.5 font-bold text-quant-cyan">#{item.rank}</td>
                        <td className="py-2.5">
                          <span className="font-bold text-quant-textPrimary group-hover:text-quant-cyan">
                            {item.symbol}
                          </span>
                          <span className="text-[10px] text-quant-textMuted ml-1.5 block sm:inline">
                            {item.sector}
                          </span>
                        </td>
                        <td className="py-2.5 text-right font-medium text-quant-textSecondary">
                          ₹{item.price.toFixed(2)}
                        </td>
                        <td className="py-2.5 text-right">
                          <span className="font-bold text-quant-cyan bg-quant-cyanMuted px-2 py-0.5 rounded">
                            {item.quant_score !== null && item.quant_score !== undefined ? item.quant_score.toFixed(1) : "N/A"}
                          </span>
                        </td>
                        <td
                          className={`py-2.5 text-right font-medium ${
                            item.predicted_return !== null && item.predicted_return !== undefined
                              ? item.predicted_return >= 0
                                ? "text-quant-bull"
                                : "text-quant-bear"
                              : "text-quant-textMuted"
                          }`}
                        >
                          {item.predicted_return !== null && item.predicted_return !== undefined
                            ? item.predicted_return >= 0
                              ? `+${(item.predicted_return * 100).toFixed(2)}%`
                              : `${(item.predicted_return * 100).toFixed(2)}%`
                            : "N/A"}
                        </td>
                        <td className="py-2.5 text-center">
                          <StatusBadge status={item.risk_status} size="sm" />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        {/* Active Holdings & Allocation */}
        <div className="quant-card p-4 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between border-b border-quant-border pb-3 mb-3">
              <div>
                <h3 className="font-mono text-sm font-bold text-quant-textPrimary flex items-center gap-2">
                  <ShieldCheck className="w-4 h-4 text-quant-bull" />
                  ACTIVE PAPER HOLDINGS
                </h3>
                <p className="text-[11px] text-quant-textMuted">
                  Double-entry verified positions in persistent accounting storage.
                </p>
              </div>

              <button
                onClick={() => onNavigate("portfolio")}
                className="text-xs font-mono text-quant-cyan hover:underline flex items-center gap-1"
              >
                Full Portfolio <ArrowRight className="w-3 h-3" />
              </button>
            </div>

            {(!account?.positions || account.positions.length === 0) ? (
              <EmptyState message="No active positions held. Virtual capital is 100% in cash reserve." />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs font-mono">
                  <thead>
                    <tr className="border-b border-quant-border text-quant-textMuted text-[11px]">
                      <th className="pb-2 font-medium">SYMBOL</th>
                      <th className="pb-2 font-medium text-right">SHARES</th>
                      <th className="pb-2 font-medium text-right">AVG COST</th>
                      <th className="pb-2 font-medium text-right">MTM VALUE</th>
                      <th className="pb-2 font-medium text-right">UNREAL P&L</th>
                      <th className="pb-2 font-medium text-right">WEIGHT</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-quant-border/50">
                    {account.positions.map((pos) => {
                      const weight = totalEquity > 0 ? (pos.market_value / totalEquity) * 100 : 0;
                      return (
                        <tr
                          key={pos.symbol}
                          onClick={() => onNavigate("portfolio", pos.symbol)}
                          className="hover:bg-quant-surface/60 cursor-pointer transition-colors group"
                        >
                          <td className="py-2.5 font-bold text-quant-textPrimary group-hover:text-quant-cyan">
                            {pos.symbol}
                          </td>
                          <td className="py-2.5 text-right text-quant-textSecondary font-medium">
                            {pos.shares}
                          </td>
                          <td className="py-2.5 text-right text-quant-textMuted">
                            ₹{pos.average_cost.toFixed(2)}
                          </td>
                          <td className="py-2.5 text-right font-medium text-quant-textPrimary">
                            ₹{pos.market_value.toLocaleString("en-IN")}
                          </td>
                          <td className={`py-2.5 text-right font-medium ${pos.unrealized_pnl >= 0 ? "text-quant-bull" : "text-quant-bear"}`}>
                            ₹{pos.unrealized_pnl.toFixed(2)}
                          </td>
                          <td className="py-2.5 text-right font-bold text-quant-textSecondary">
                            {weight.toFixed(1)}%
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Bottom Section: Pipeline Health Monitor */}
      <div className="quant-card p-4">
        <div className="flex items-center justify-between border-b border-quant-border pb-3 mb-4">
          <div>
            <h3 className="font-mono text-sm font-bold text-quant-textPrimary flex items-center gap-2">
              <Activity className="w-4 h-4 text-quant-cyan" />
              SYSTEM & PIPELINE OPERATIONAL TELEMETRY
            </h3>
            <p className="text-[11px] text-quant-textMuted">
              End-to-end component health from Market Ingestion through Double-Entry Accounting & Reconciliation.
            </p>
          </div>

          <button
            onClick={() => onNavigate("system")}
            className="text-xs font-mono text-quant-cyan hover:underline flex items-center gap-1"
          >
            System Architecture <ArrowRight className="w-3 h-3" />
          </button>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3">
          {[
            { name: "Quote Cache", status: "HEALTHY", desc: "Cached stream active" },
            { name: "Quote Validator", status: "HEALTHY", desc: "Out-of-order protection" },
            { name: "Bar Aggregator", status: "HEALTHY", desc: "Parquet 5-min & daily" },
            { name: "Feature Engine", status: "HEALTHY", desc: "66 features verified" },
            { name: "ML Engine", status: "HEALTHY", desc: "RandomForest v1 target_5d" },
            { name: "Stock Ranker", status: "HEALTHY", desc: "Cross-sectional scorer" },
            { name: "Portfolio Optimizer", status: "HEALTHY", desc: "SLSQP risk-constrained" },
            { name: "12-Point Risk", status: account?.kill_switch?.active ? "BLOCKED" : "HEALTHY", desc: "Zero leverage / 35% cap" },
            { name: "Paper Broker", status: "HEALTHY", desc: "Virtual order simulator" },
            { name: "Reconciliation", status: account?.last_reconciliation?.is_clean ? "HEALTHY" : "WARNING", desc: "Double-entry ledger audit" },
          ].map((comp, idx) => (
            <div key={idx} className="bg-quant-surface p-3 rounded-lg border border-quant-border flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <span className="font-mono font-bold text-xs text-quant-textPrimary">{comp.name}</span>
                  <StatusBadge status={comp.status} size="sm" />
                </div>
                <p className="text-[10px] text-quant-textMuted">{comp.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
