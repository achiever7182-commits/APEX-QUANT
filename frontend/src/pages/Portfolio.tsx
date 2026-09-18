import React, { useEffect, useState } from "react";
import { PieChart, ShieldAlert, TrendingUp, DollarSign, Layers } from "lucide-react";
import { api } from "../api/client";
import { LoadingState, ErrorState, EmptyState } from "../components/ErrorState";
import { MetricCard } from "../components/MetricCard";
import { AllocationBarChart } from "../charts/AllocationBarChart";
import type { AccountSummary, Position, UniverseConstituent } from "../types";

interface PortfolioProps {
  onSelectStock: (symbol: string) => void;
}

export const Portfolio: React.FC<PortfolioProps> = ({ onSelectStock }) => {
  const [account, setAccount] = useState<AccountSummary | null>(null);
  const [universe, setUniverse] = useState<Record<string, UniverseConstituent>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchPortfolio = async () => {
    try {
      setError(null);
      const [acctRes, uRes] = await Promise.all([
        api.getAccountSummary(),
        api.getUniverse().catch(() => ({ count: 0, universe: [] })),
      ]);
      setAccount(acctRes);
      const map: Record<string, UniverseConstituent> = {};
      (uRes.universe || []).forEach((u) => {
        map[u.symbol] = u;
      });
      setUniverse(map);
    } catch (err: any) {
      setError(err?.message || "Failed to load paper portfolio state.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPortfolio();
    const interval = setInterval(fetchPortfolio, 10000);
    return () => clearInterval(interval);
  }, []);

  if (loading) return <LoadingState message="Loading double-entry paper positions & NAV telemetry..." />;
  if (error && !account) return <ErrorState message={error} onRetry={fetchPortfolio} />;

  const formatCurrency = (val?: number | null, decimals = 2) =>
    val !== undefined && val !== null
      ? `₹${val.toLocaleString("en-IN", { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}`
      : "N/A";
  const formatPct = (val?: number | null, decimals = 2) =>
    val !== undefined && val !== null ? `${val.toFixed(decimals)}%` : "N/A";

  const totalEquity = account?.total_equity;
  const positions = account?.positions || [];

  // Prepare allocation items
  const positionAllocations = positions.map((p) => {
    const weight = totalEquity && totalEquity > 0 ? (p.market_value / totalEquity) * 100 : 0;
    const meta = universe[p.symbol];
    return {
      label: p.symbol,
      sublabel: meta?.sector || "General",
      value: p.market_value,
      weightPct: weight,
      limitPct: 35.0, // 35% single-stock limit
    };
  });

  // Calculate sector allocations
  const sectorMap: Record<string, number> = {};
  positions.forEach((p) => {
    const sec = universe[p.symbol]?.sector || "General";
    sectorMap[sec] = (sectorMap[sec] || 0) + p.market_value;
  });

  const sectorAllocations = Object.entries(sectorMap).map(([sec, val]) => {
    const weight = totalEquity && totalEquity > 0 ? (val / totalEquity) * 100 : 0;
    return {
      label: sec,
      value: val,
      weightPct: weight,
      limitPct: 55.0, // 55% sector limit
    };
  });

  const drawdownPct = account?.max_drawdown !== undefined ? account.max_drawdown * 100 : undefined;
  const grossExposurePct = totalEquity && totalEquity > 0 && account?.positions_value !== undefined
    ? (account.positions_value / totalEquity) * 100
    : undefined;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-quant-border pb-3">
        <div>
          <h2 className="font-mono text-lg font-bold text-quant-textPrimary flex items-center gap-2">
            PORTFOLIO ACCOUNTING
            <span className="text-xs font-normal text-quant-warn bg-quant-warnMuted px-2 py-0.5 rounded border border-quant-warn/30">
              PAPER PORTFOLIO
            </span>
          </h2>
          <p className="text-xs text-quant-textSecondary">
            Persistent mark-to-market position ledger, cash balances, cost basis, and concentration metrics.
          </p>
        </div>

        <div className="text-xs font-mono text-quant-textMuted flex items-center gap-2">
          <span>Initial Capital:</span>
          <span className="text-quant-textPrimary font-semibold">
            {formatCurrency(account?.initial_capital)}
          </span>
        </div>
      </div>

      {/* Top Portfolio Metrics (8 cards) */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3.5">
        <MetricCard
          title="TOTAL EQUITY"
          value={formatCurrency(account?.total_equity)}
          subtitle="NAV Mark-to-Market"
          tooltip="Total portfolio equity value."
          accentColor="cyan"
        />

        <MetricCard
          title="AVAILABLE CASH"
          value={formatCurrency(account?.cash)}
          subtitle={
            account?.cash !== undefined && totalEquity && totalEquity > 0
              ? `${((account.cash / totalEquity) * 100).toFixed(1)}% Weight`
              : "Weight: N/A"
          }
          tooltip="Liquid cash available for orders."
          accentColor="default"
        />

        <MetricCard
          title="INVESTED VALUE"
          value={formatCurrency(account?.positions_value)}
          subtitle={`${positions.length} Active Positions`}
          tooltip="Total market value of held shares."
          accentColor="default"
        />

        <MetricCard
          title="TODAY'S P&L"
          value={formatCurrency(account?.daily_pnl)}
          change={
            totalEquity && totalEquity > 0 && account?.daily_pnl !== undefined
              ? (account.daily_pnl / totalEquity) * 100
              : undefined
          }
          tooltip="Intraday profit/loss based on start of day equity."
          accentColor={account?.daily_pnl !== undefined ? (account.daily_pnl >= 0 ? "bull" : "bear") : "default"}
        />

        <MetricCard
          title="UNREALIZED P&L"
          value={formatCurrency(account?.unrealized_pnl)}
          subtitle="Mark-to-market"
          tooltip="Paper profit/loss on currently open positions."
          accentColor={account?.unrealized_pnl !== undefined ? (account.unrealized_pnl >= 0 ? "bull" : "bear") : "default"}
        />

        <MetricCard
          title="REALIZED P&L"
          value={formatCurrency(account?.realized_pnl)}
          subtitle="Closed trades"
          tooltip="Net realized profit/loss after closed paper trades."
          accentColor={account?.realized_pnl !== undefined ? (account.realized_pnl >= 0 ? "bull" : "bear") : "default"}
        />

        <MetricCard
          title="MAX DRAWDOWN"
          value={formatPct(drawdownPct)}
          subtitle="Cap: 10.00%"
          tooltip="Maximum peak-to-trough decline."
          accentColor={drawdownPct !== undefined && drawdownPct > 5 ? "warn" : "default"}
        />

        <MetricCard
          title="GROSS EXPOSURE"
          value={formatPct(grossExposurePct, 1)}
          subtitle="Cap: 100.0%"
          tooltip="Positions value divided by equity."
          accentColor="default"
        />
      </div>

      {/* Holdings Table */}
      <div className="quant-card overflow-hidden">
        <div className="p-4 border-b border-quant-border flex items-center justify-between">
          <div className="flex items-center gap-2">
            <PieChart className="w-4 h-4 text-quant-cyan" />
            <h3 className="font-mono text-xs font-bold text-quant-textPrimary">
              HOLDINGS LEDGER (DOUBLE-ENTRY VERIFIED)
            </h3>
          </div>
          <span className="text-[11px] font-mono text-quant-textMuted">
            {positions.length} Active Positions
          </span>
        </div>

        {positions.length === 0 ? (
          <EmptyState message="No positions currently open. All assets in cash." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs font-mono">
              <thead className="bg-quant-surface border-b border-quant-border text-quant-textMuted text-[11px]">
                <tr>
                  <th className="p-3 font-medium">SYMBOL</th>
                  <th className="p-3 font-medium">SECTOR</th>
                  <th className="p-3 font-medium text-right">QUANTITY</th>
                  <th className="p-3 font-medium text-right">AVG COST</th>
                  <th className="p-3 font-medium text-right">CURRENT PRICE</th>
                  <th className="p-3 font-medium text-right">MARKET VALUE</th>
                  <th className="p-3 font-medium text-right">UNREAL P&L</th>
                  <th className="p-3 font-medium text-right">WEIGHT</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-quant-border">
                {positions.map((pos) => {
                  const weight = totalEquity > 0 ? (pos.market_value / totalEquity) * 100 : 0;
                  const meta = universe[pos.symbol];
                  const isPosPnl = pos.unrealized_pnl >= 0;

                  return (
                    <tr
                      key={pos.symbol}
                      onClick={() => onSelectStock(pos.symbol)}
                      className="hover:bg-quant-surface/60 cursor-pointer transition-colors group"
                    >
                      <td className="p-3 font-bold text-quant-textPrimary group-hover:text-quant-cyan">
                        {pos.symbol}
                      </td>

                      <td className="p-3 text-quant-textSecondary">
                        {meta?.sector || "General"}
                      </td>

                      <td className="p-3 text-right font-medium text-quant-textPrimary">
                        {pos.shares}
                      </td>

                      <td className="p-3 text-right text-quant-textMuted">
                        ₹{pos.average_cost.toFixed(2)}
                      </td>

                      <td className="p-3 text-right font-medium text-quant-textSecondary">
                        ₹{pos.current_price.toFixed(2)}
                      </td>

                      <td className="p-3 text-right font-bold text-quant-textPrimary">
                        ₹{pos.market_value.toLocaleString("en-IN")}
                      </td>

                      <td className={`p-3 text-right font-bold ${isPosPnl ? "text-quant-bull" : "text-quant-bear"}`}>
                        {isPosPnl ? `+₹${pos.unrealized_pnl.toFixed(2)}` : `₹${pos.unrealized_pnl.toFixed(2)}`}
                      </td>

                      <td className="p-3 text-right">
                        <span className={`font-bold ${weight > 35 ? "text-quant-bear" : "text-quant-cyan"}`}>
                          {weight.toFixed(1)}%
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Allocation Charts */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <AllocationBarChart
          title="SINGLE STOCK CONCENTRATION (MAX 35% LIMIT)"
          items={positionAllocations}
          maxScale={40}
        />

        <AllocationBarChart
          title="SECTOR ALLOCATION EXPOSURE (MAX 55% LIMIT)"
          items={sectorAllocations}
          maxScale={60}
        />
      </div>
    </div>
  );
};
