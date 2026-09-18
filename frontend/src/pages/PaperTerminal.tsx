import React, { useEffect, useState } from "react";
import { Terminal, Play, Power, RefreshCw, AlertTriangle, ShieldCheck, CheckCircle2, FastForward, Clock, History, Cpu, StopCircle, Layers } from "lucide-react";
import { api } from "../api/client";
import { LoadingState, ErrorState, EmptyState } from "../components/ErrorState";
import { MetricCard } from "../components/MetricCard";
import { StatusBadge } from "../components/StatusBadge";
import type { AccountSummary, OperationalTelemetry, Order, PaperPerformanceReport, Position, ReconciliationReport, SessionRecord } from "../types";

interface PaperTerminalProps {
  onOpenKillSwitchModal: () => void;
  onSelectStock: (symbol: string) => void;
}

export const PaperTerminal: React.FC<PaperTerminalProps> = ({
  onOpenKillSwitchModal,
  onSelectStock,
}) => {
  const [account, setAccount] = useState<AccountSummary | null>(null);
  const [orders, setOrders] = useState<Order[]>([]);
  const [recon, setRecon] = useState<ReconciliationReport | null>(null);
  const [telemetry, setTelemetry] = useState<OperationalTelemetry | null>(null);
  const [sessions, setSessions] = useState<SessionRecord[]>([]);
  const [simPerf, setSimPerf] = useState<PaperPerformanceReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [executingCycle, setExecutingCycle] = useState(false);
  const [simRunning, setSimRunning] = useState(false);
  const [simCount, setSimCount] = useState<number>(5);
  const [simSeed, setSimSeed] = useState<number>(42);
  const [cycleSuccessMsg, setCycleSuccessMsg] = useState<string | null>(null);
  const [simSuccessMsg, setSimSuccessMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchState = async () => {
    try {
      setError(null);
      const [acctRes, ordRes, recRes, telemRes, sessRes] = await Promise.all([
        api.getAccountSummary(),
        api.getOrders(),
        api.getReconciliation().catch(() => null),
        api.getPaperTelemetry().catch(() => null),
        api.getPaperSessions().catch(() => ({ count: 0, sessions: [] })),
      ]);
      setAccount(acctRes);
      setOrders(ordRes || []);
      if (recRes) setRecon(recRes);
      if (telemRes) setTelemetry(telemRes);
      if (sessRes && sessRes.sessions) setSessions(sessRes.sessions);
    } catch (err: any) {
      setError(err?.message || "Failed to load paper execution state.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchState();
    const interval = setInterval(fetchState, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleRunCycle = async () => {
    setExecutingCycle(true);
    setError(null);
    setCycleSuccessMsg(null);
    try {
      const res = await api.runPaperCycle();
      setCycleSuccessMsg(`Cycle ${res?.cycle_id || "executed"} completed successfully.`);
      await fetchState();
    } catch (err: any) {
      setError(err?.message || "Cycle execution failed.");
    } finally {
      setExecutingCycle(false);
    }
  };

  const handleRunSimulation = async (countOverride?: number) => {
    const count = countOverride || simCount;
    setSimRunning(true);
    setError(null);
    setSimSuccessMsg(null);
    try {
      const res = await api.runPaperSimulation({
        sessions_count: count,
        random_seed: simSeed,
      });
      if (res?.performance) {
        setSimPerf(res.performance);
      }
      setSimSuccessMsg(`Multi-session simulation (${count} sessions) executed successfully.`);
      await fetchState();
    } catch (err: any) {
      setError(err?.message || "Multi-session simulation failed.");
    } finally {
      setSimRunning(false);
    }
  };

  const handleStopSimulation = async () => {
    try {
      await api.stopPaperSimulation();
      setSimRunning(false);
      await fetchState();
    } catch (err: any) {
      setError(err?.message || "Failed to abort simulation.");
    }
  };

  if (loading) return <LoadingState message="Connecting to PaperTradingEngine & OrderManager..." />;
  if (error && !account) return <ErrorState message={error} onRetry={fetchState} />;

  const isKillSwitchActive = account?.kill_switch?.active ?? false;
  const positions = account?.positions || [];

  const formatCurrency = (val?: number | null) =>
    val !== undefined && val !== null
      ? `₹${val.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
      : "N/A";

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-quant-border pb-3">
        <div>
          <h2 className="font-mono text-lg font-bold text-quant-textPrimary flex items-center gap-2">
            PAPER TRADING TERMINAL
            <span className="text-xs font-normal text-quant-cyan bg-quant-cyanMuted px-2 py-0.5 rounded border border-quant-cyan/30">
              VIRTUAL BROKER SANDBOX
            </span>
          </h2>
          <p className="text-xs text-quant-textSecondary">
            Manual execution controls, live cycle runner, order book, and real-time ledger accounting.
          </p>
        </div>

        {/* Execution Controls */}
        <div className="flex items-center gap-3">
          <button
            onClick={handleRunCycle}
            disabled={executingCycle || isKillSwitchActive}
            className="flex items-center gap-2 px-4 py-2 bg-quant-cyan hover:bg-quant-cyan/90 text-quant-bg font-mono font-bold text-xs rounded-lg transition-all shadow-md disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Play className={`w-3.5 h-3.5 fill-current ${executingCycle ? "animate-spin" : ""}`} />
            <span>{executingCycle ? "Executing Cycle..." : "Execute Rebalance Cycle"}</span>
          </button>

          <button
            onClick={onOpenKillSwitchModal}
            className={`flex items-center gap-1.5 px-3 py-2 rounded-lg font-mono text-xs font-bold border transition-colors ${
              isKillSwitchActive
                ? "bg-quant-bear text-white border-quant-bear animate-pulse"
                : "bg-quant-card text-quant-warn border-quant-border hover:border-quant-warn"
            }`}
          >
            <Power className="w-3.5 h-3.5" />
            <span>{isKillSwitchActive ? "Resume Orders" : "Pause Orders"}</span>
          </button>
        </div>
      </div>

      {/* Notice & Feedback */}
      {cycleSuccessMsg && (
        <div className="p-3 bg-quant-bullMuted border border-quant-bull/40 text-quant-bull font-mono text-xs rounded flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4" />
          {cycleSuccessMsg}
        </div>
      )}

      {isKillSwitchActive && (
        <div className="p-3 bg-quant-bearMuted border border-quant-bear/40 text-quant-bear font-mono text-xs rounded flex items-center gap-2">
          <AlertTriangle className="w-4 h-4" />
          PAPER ORDER SUBMISSION IS CURRENTLY BLOCKED BY THE PERSISTENT KILL SWITCH.
        </div>
      )}

      {/* KPI Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3.5">
        <MetricCard
          title="STARTING CAPITAL"
          value={formatCurrency(account?.initial_capital)}
          subtitle="Fixed Virtual Baseline"
          tooltip="Initial paper sandbox virtual capital."
          accentColor="default"
        />

        <MetricCard
          title="TOTAL EQUITY"
          value={formatCurrency(account?.total_equity)}
          subtitle="Current NAV"
          tooltip="Current liquid cash plus mark-to-market positions."
          accentColor="cyan"
        />

        <MetricCard
          title="AVAILABLE CASH"
          value={formatCurrency(account?.cash)}
          subtitle={
            account?.cash !== undefined && account?.total_equity && account.total_equity > 0
              ? `${((account.cash / account.total_equity) * 100).toFixed(1)}% Cash Reserve`
              : "Cash Reserve: N/A"
          }
          tooltip="Available cash for new allocations."
          accentColor="default"
        />

        <MetricCard
          title="TODAY'S P&L"
          value={formatCurrency(account?.daily_pnl)}
          change={
            account?.total_equity && account.total_equity > 0 && account.daily_pnl !== undefined
              ? (account.daily_pnl / account.total_equity) * 100
              : undefined
          }
          tooltip="Intraday profit/loss based on start-of-day equity."
          accentColor={account?.daily_pnl !== undefined ? (account.daily_pnl >= 0 ? "bull" : "bear") : "default"}
        />
      </div>

      {/* Positions & Recent Orders Ledger */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Positions */}
        <div className="quant-card p-4">
          <div className="flex items-center justify-between pb-3 border-b border-quant-border mb-3">
            <h3 className="font-mono text-xs font-bold text-quant-textPrimary flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-quant-cyan" />
              ACTIVE EQUITY POSITIONS ({positions.length})
            </h3>
            <span className="text-[11px] font-mono text-quant-textMuted">Mark-to-Market</span>
          </div>

          {positions.length === 0 ? (
            <EmptyState message="Zero active positions. All virtual capital in liquid cash." />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs font-mono">
                <thead className="bg-quant-surface border-b border-quant-border text-quant-textMuted text-[11px]">
                  <tr>
                    <th className="p-2.5 font-medium">SYMBOL</th>
                    <th className="p-2.5 font-medium text-right">SHARES</th>
                    <th className="p-2.5 font-medium text-right">AVG COST</th>
                    <th className="p-2.5 font-medium text-right">PRICE</th>
                    <th className="p-2.5 font-medium text-right">UNREAL P&L</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-quant-border">
                  {positions.map((p) => (
                    <tr
                      key={p.symbol}
                      onClick={() => onSelectStock(p.symbol)}
                      className="hover:bg-quant-surface/60 cursor-pointer transition-colors"
                    >
                      <td className="p-2.5 font-bold text-quant-textPrimary hover:text-quant-cyan">
                        {p.symbol}
                      </td>
                      <td className="p-2.5 text-right font-medium text-quant-textPrimary">
                        {p.shares}
                      </td>
                      <td className="p-2.5 text-right text-quant-textMuted">
                        ₹{p.average_cost.toFixed(2)}
                      </td>
                      <td className="p-2.5 text-right font-medium text-quant-textSecondary">
                        ₹{p.current_price.toFixed(2)}
                      </td>
                      <td className={`p-2.5 text-right font-bold ${p.unrealized_pnl >= 0 ? "text-quant-bull" : "text-quant-bear"}`}>
                        ₹{p.unrealized_pnl.toFixed(2)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Orders */}
        <div className="quant-card p-4">
          <div className="flex items-center justify-between pb-3 border-b border-quant-border mb-3">
            <h3 className="font-mono text-xs font-bold text-quant-textPrimary flex items-center gap-2">
              <Terminal className="w-4 h-4 text-quant-cyan" />
              RECENT PAPER ORDERS ({orders.length})
            </h3>
            <span className="text-[11px] font-mono text-quant-textMuted">Ledger Log</span>
          </div>

          {orders.length === 0 ? (
            <EmptyState message="No orders recorded in session." />
          ) : (
            <div className="overflow-x-auto max-h-[300px] overflow-y-auto">
              <table className="w-full text-left text-xs font-mono">
                <thead className="bg-quant-surface border-b border-quant-border text-quant-textMuted text-[11px] sticky top-0">
                  <tr>
                    <th className="p-2.5 font-medium">ORDER ID</th>
                    <th className="p-2.5 font-medium">SYMBOL</th>
                    <th className="p-2.5 font-medium">SIDE</th>
                    <th className="p-2.5 font-medium text-right">QTY</th>
                    <th className="p-2.5 font-medium text-center">STATUS</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-quant-border">
                  {orders.slice(0, 10).map((o) => (
                    <tr key={o.order_id} className="hover:bg-quant-surface/60 transition-colors">
                      <td className="p-2.5 font-bold text-quant-textSecondary text-[11px]">
                        {o.order_id}
                      </td>
                      <td className="p-2.5 font-bold text-quant-textPrimary">
                        {o.symbol}
                      </td>
                      <td className="p-2.5">
                        <span className={`px-1.5 py-0.2 rounded text-[10px] font-bold ${o.side === "BUY" ? "text-quant-bull" : "text-quant-bear"}`}>
                          {o.side}
                        </span>
                      </td>
                      <td className="p-2.5 text-right font-medium text-quant-textPrimary">
                        {o.filled_quantity} / {o.requested_quantity}
                      </td>
                      <td className="p-2.5 text-center">
                        <StatusBadge status={o.status} size="sm" />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Multi-Session Simulation & Operational Audit Trail (Step 13) */}
      <div className="quant-card p-4 space-y-4 border border-quant-border">
        {/* Section Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-quant-border pb-3">
          <div>
            <h3 className="font-mono text-sm font-bold text-quant-textPrimary flex items-center gap-2">
              <FastForward className="w-4 h-4 text-quant-cyan" />
              MULTI-SESSION PAPER SIMULATION & OPERATIONAL AUDIT
            </h3>
            <p className="text-xs text-quant-textSecondary">
              Run continuous simulated market sessions across NSE trading days to test lifecycle state machines, accounting invariants, and crash recovery.
            </p>
          </div>

          {/* Simulation Controls */}
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex items-center gap-1 bg-quant-surface px-2 py-1 rounded border border-quant-border text-xs font-mono">
              <span className="text-quant-textMuted">SEED:</span>
              <input
                type="number"
                value={simSeed}
                onChange={(e) => setSimSeed(parseInt(e.target.value) || 0)}
                className="w-16 bg-transparent text-quant-textPrimary text-center focus:outline-none"
              />
            </div>

            <div className="flex items-center gap-1">
              <button
                onClick={() => handleRunSimulation(5)}
                disabled={simRunning || isKillSwitchActive}
                className="px-2.5 py-1 bg-quant-surface hover:bg-quant-surface/80 border border-quant-border text-quant-textSecondary hover:text-quant-cyan text-xs font-mono rounded transition-colors disabled:opacity-50"
              >
                5 Sessions
              </button>
              <button
                onClick={() => handleRunSimulation(20)}
                disabled={simRunning || isKillSwitchActive}
                className="px-2.5 py-1 bg-quant-surface hover:bg-quant-surface/80 border border-quant-border text-quant-textSecondary hover:text-quant-cyan text-xs font-mono rounded transition-colors disabled:opacity-50"
              >
                20 Sessions
              </button>
              <button
                onClick={() => handleRunSimulation(60)}
                disabled={simRunning || isKillSwitchActive}
                className="px-2.5 py-1 bg-quant-surface hover:bg-quant-surface/80 border border-quant-border text-quant-textSecondary hover:text-quant-cyan text-xs font-mono rounded transition-colors disabled:opacity-50"
              >
                60 Sessions
              </button>
            </div>

            {simRunning ? (
              <button
                onClick={handleStopSimulation}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-quant-bear text-white text-xs font-mono font-bold rounded-lg transition-colors shadow-md"
              >
                <StopCircle className="w-3.5 h-3.5" />
                <span>Abort Simulation</span>
              </button>
            ) : (
              <button
                onClick={() => handleRunSimulation()}
                disabled={isKillSwitchActive}
                className="flex items-center gap-1.5 px-3.5 py-1.5 bg-quant-cyan hover:bg-quant-cyan/90 text-quant-bg text-xs font-mono font-bold rounded-lg transition-colors shadow-md disabled:opacity-50"
              >
                <Play className="w-3.5 h-3.5 fill-current" />
                <span>Run Simulation</span>
              </button>
            )}
          </div>
        </div>

        {/* Simulation Feedback Notice */}
        {simSuccessMsg && (
          <div className="p-3 bg-quant-bullMuted border border-quant-bull/40 text-quant-bull font-mono text-xs rounded flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4" />
            {simSuccessMsg}
          </div>
        )}

        {/* Mandatory Research Disclosure Banner */}
        <div className="p-2.5 bg-quant-surface border border-quant-border rounded text-[11px] font-mono text-quant-textMuted flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-quant-warn flex-shrink-0" />
          <span>
            <strong className="text-quant-warn">SIMULATED PAPER PERFORMANCE — NOT LIVE TRADING:</strong> All returns, NAV marks, and Sharpe metrics represent point-in-time simulated paper trading with 10 bps fees and 5 bps slippage. Zero real broker execution.
          </span>
        </div>

        {/* Telemetry Quick Summary Strip */}
        <div className="grid grid-cols-2 sm:grid-cols-6 gap-2.5 text-xs font-mono">
          <div className="bg-quant-surface p-2.5 rounded border border-quant-border">
            <span className="text-quant-textMuted text-[10px] block">SESSIONS</span>
            <span className="text-quant-textPrimary font-bold">
              {telemetry?.sessions_completed ?? sessions.length} / {telemetry?.sessions_started ?? sessions.length}
            </span>
            <span className="text-[10px] text-quant-textSecondary block">Completed</span>
          </div>

          <div className="bg-quant-surface p-2.5 rounded border border-quant-border">
            <span className="text-quant-textMuted text-[10px] block">CYCLES</span>
            <span className="text-quant-cyan font-bold">{telemetry?.cycles_completed ?? "0"}</span>
            <span className="text-[10px] text-quant-textSecondary block">Avg {telemetry?.average_cycle_latency ?? 0}ms</span>
          </div>

          <div className="bg-quant-surface p-2.5 rounded border border-quant-border">
            <span className="text-quant-textMuted text-[10px] block">ORDERS / FILLS</span>
            <span className="text-quant-textPrimary font-bold">
              {telemetry?.orders_filled ?? 0} / {telemetry?.orders_generated ?? orders.length}
            </span>
            <span className="text-[10px] text-quant-textSecondary block">Zero Collisions</span>
          </div>

          <div className="bg-quant-surface p-2.5 rounded border border-quant-border">
            <span className="text-quant-textMuted text-[10px] block">RISK REJECTIONS</span>
            <span className="text-quant-warn font-bold">{telemetry?.risk_rejections ?? 0}</span>
            <span className="text-[10px] text-quant-textSecondary block">12-pt Checks</span>
          </div>

          <div className="bg-quant-surface p-2.5 rounded border border-quant-border">
            <span className="text-quant-textMuted text-[10px] block">RECOVERIES</span>
            <span className="text-quant-bull font-bold">{telemetry?.restart_recoveries ?? 0}</span>
            <span className="text-[10px] text-quant-textSecondary block">Crash Resumptions</span>
          </div>

          <div className="bg-quant-surface p-2.5 rounded border border-quant-border">
            <span className="text-quant-textMuted text-[10px] block">RECONCILIATION</span>
            <span className="text-quant-bull font-bold">
              {telemetry?.last_reconciliation_status || recon?.status || "CLEAN"}
            </span>
            <span className="text-[10px] text-quant-textSecondary block">Zero Discrepancies</span>
          </div>
        </div>

        {/* Persistent Session History Table */}
        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs font-mono">
            <span className="font-bold text-quant-textPrimary flex items-center gap-1.5">
              <History className="w-3.5 h-3.5 text-quant-cyan" />
              SIMULATION SESSION HISTORY ({sessions.length})
            </span>
            <span className="text-[11px] text-quant-textMuted">Persisted to data/paper/sessions/</span>
          </div>

          {sessions.length === 0 ? (
            <EmptyState message="No multi-session simulation executed yet. Click a session preset above to begin." />
          ) : (
            <div className="overflow-x-auto max-h-[300px] overflow-y-auto border border-quant-border rounded">
              <table className="w-full text-left text-xs font-mono">
                <thead className="bg-quant-surface border-b border-quant-border text-quant-textMuted text-[11px] sticky top-0">
                  <tr>
                    <th className="p-2.5 font-medium">SESSION ID</th>
                    <th className="p-2.5 font-medium">DATE</th>
                    <th className="p-2.5 font-medium">STATE</th>
                    <th className="p-2.5 font-medium text-right">CYCLES</th>
                    <th className="p-2.5 font-medium text-right">ORDERS</th>
                    <th className="p-2.5 font-medium text-right">EQUITY</th>
                    <th className="p-2.5 font-medium text-right">CASH</th>
                    <th className="p-2.5 font-medium text-center">RECON</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-quant-border">
                  {sessions.slice(0, 15).map((s) => (
                    <tr key={s.session_id} className="hover:bg-quant-surface/60 transition-colors">
                      <td className="p-2.5 font-bold text-quant-textPrimary text-[11px]">{s.session_id}</td>
                      <td className="p-2.5 text-quant-textSecondary">{s.simulation_date}</td>
                      <td className="p-2.5">
                        <StatusBadge status={s.state} size="sm" />
                      </td>
                      <td className="p-2.5 text-right text-quant-textPrimary">{s.cycle_count}</td>
                      <td className="p-2.5 text-right text-quant-textSecondary">{s.fills_count} / {s.orders_count}</td>
                      <td className="p-2.5 text-right font-bold text-quant-textPrimary">{formatCurrency(s.equity)}</td>
                      <td className="p-2.5 text-right text-quant-textMuted">{formatCurrency(s.cash)}</td>
                      <td className="p-2.5 text-center">
                        <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${s.reconciliation_status === "MATCH" || s.reconciliation_status === "CLEAN" ? "text-quant-bull" : "text-quant-warn"}`}>
                          {s.reconciliation_status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
