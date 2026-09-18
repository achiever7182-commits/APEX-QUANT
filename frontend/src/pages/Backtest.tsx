import React, { useEffect, useState } from "react";
import { FlaskConical, AlertTriangle, TrendingUp, BarChart3, Layers, Calendar, CheckCircle } from "lucide-react";
import { api } from "../api/client";
import { LoadingState, ErrorState } from "../components/ErrorState";
import { MetricCard } from "../components/MetricCard";
import { Tooltip } from "../components/Tooltip";
import { EquityCurveChart } from "../charts/EquityCurveChart";
import type { BacktestResults, StrategyMetrics } from "../types";

export const Backtest: React.FC = () => {
  const [data, setData] = useState<BacktestResults | null>(null);
  const [selectedStrategy, setSelectedStrategy] = useState<string>("constrained");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getBacktestResults()
      .then((res) => setData(res))
      .catch((err) => setError(err?.message || "Failed to load backtest lab results."))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <LoadingState message="Loading historical walk-forward backtest simulations & benchmark curves..." />;
  if (error || !data) return <ErrorState message={error || "Backtest data not available."} />;

  const isUnavailable = data.status === "unavailable" || !data.strategies || Object.keys(data.strategies).length === 0;

  if (isUnavailable) {
    return (
      <div className="space-y-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-quant-border pb-3">
          <div>
            <h2 className="font-mono text-lg font-bold text-quant-textPrimary flex items-center gap-2">
              BACKTEST LAB
              <span className="text-xs font-normal text-quant-warn bg-quant-warnMuted px-2 py-0.5 rounded border border-quant-warn/30">
                HISTORICAL RESEARCH SIMULATION
              </span>
            </h2>
            <p className="text-xs text-quant-textSecondary">
              Event-driven historical simulation under zero-lookahead, integer share sizing, and friction cost assumptions.
            </p>
          </div>
        </div>

        {/* Unavailable State Notice */}
        <div className="quant-card p-8 text-center space-y-4">
          <div className="w-12 h-12 rounded-full bg-quant-warnMuted border border-quant-warn/30 flex items-center justify-center mx-auto text-quant-warn">
            <AlertTriangle className="w-6 h-6" />
          </div>
          <div>
            <h3 className="font-mono text-base font-bold text-quant-textPrimary uppercase">
              HISTORICAL RESEARCH SIMULATION — DATA UNAVAILABLE
            </h3>
            <p className="text-xs font-mono text-quant-textSecondary max-w-xl mx-auto mt-2 leading-relaxed">
              {data.message || "Historical walk-forward backtest results are unavailable on disk."}
              <br />
              APEX-QUANT enforces strict data integrity: performance metrics, Sharpe ratios,
              and CAGR figures are never estimated, simulated with fake defaults, or hardcoded.
            </p>
          </div>

          <div className="p-3 bg-quant-surface rounded-lg border border-quant-border max-w-lg mx-auto text-left">
            <div className="text-[11px] font-mono text-quant-cyan font-bold mb-1">
              RESEARCH DISCLAIMER
            </div>
            <p className="text-[11px] font-mono text-quant-textMuted leading-relaxed">
              {data.disclaimer}
            </p>
          </div>
        </div>
      </div>
    );
  }

  const currentStrat: StrategyMetrics = data.strategies[selectedStrategy] || Object.values(data.strategies)[0];

  const formatPct = (val?: number | null, withSign = false) =>
    val !== undefined && val !== null ? `${withSign && val > 0 ? "+" : ""}${val.toFixed(2)}%` : "N/A";
  const formatNum = (val?: number | null, decimals = 3) =>
    val !== undefined && val !== null ? val.toFixed(decimals) : "N/A";
  const formatCurrency = (val?: number | null) =>
    val !== undefined && val !== null ? `₹${val.toLocaleString("en-IN")}` : "N/A";

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-quant-border pb-3">
        <div>
          <h2 className="font-mono text-lg font-bold text-quant-textPrimary flex items-center gap-2">
            BACKTEST LAB
            <span className="text-xs font-normal text-quant-cyan bg-quant-cyanMuted px-2 py-0.5 rounded border border-quant-cyan/30">
              HISTORICAL RESEARCH SIMULATION
            </span>
          </h2>
          <p className="text-xs text-quant-textSecondary">
            Event-driven historical simulation under zero-lookahead, integer share sizing, and friction cost assumptions.
          </p>
        </div>

        <div className="text-xs font-mono text-quant-textMuted flex items-center gap-2">
          <span>Window:</span>
          <span className="text-quant-textPrimary font-semibold">
            {data.period ? `${data.period.start_date} to ${data.period.end_date} (${data.period.duration_months} Months)` : "N/A"}
          </span>
        </div>
      </div>

      {/* Mandatory Honest Simulation Banner */}
      <div className="bg-quant-card border-l-4 border-quant-cyan p-4 rounded-r-lg">
        <div className="flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-quant-cyan shrink-0 mt-0.5" />
          <div className="text-xs leading-relaxed">
            <h4 className="font-mono font-bold text-quant-cyan uppercase mb-1">
              HISTORICAL RESEARCH SIMULATION — ZERO PROFITABILITY GUARANTEES
            </h4>
            <p className="text-quant-textSecondary">
              Past simulated performance does not guarantee or imply future profitability. Friction costs (10 bps brokerage + 5 bps slippage)
              and single-stock position limits (35%) are enforced. Evaluation executed strictly on the 5-stock empirical benchmark dataset.
            </p>
          </div>
        </div>
      </div>

      {/* Strategy Switcher */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-mono text-quant-textMuted mr-2">ALLOCATION STRATEGY:</span>
        {Object.entries(data.strategies).map(([key, strat]) => (
          <button
            key={key}
            onClick={() => setSelectedStrategy(key)}
            className={`px-3 py-1.5 rounded text-xs font-mono font-medium transition-all ${
              selectedStrategy === key
                ? "bg-quant-cyan text-quant-bg font-bold shadow-sm"
                : "bg-quant-card text-quant-textSecondary hover:text-quant-textPrimary hover:bg-quant-surface border border-quant-border"
            }`}
          >
            {strat.name}
          </button>
        ))}
      </div>

      {/* Primary Strategy Metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3.5">
        <MetricCard
          title="TOTAL RETURN"
          value={formatPct(currentStrat?.total_return_pct, true)}
          subtitle={currentStrat?.final_equity !== undefined ? `Final: ${formatCurrency(currentStrat.final_equity)}` : "Final: N/A"}
          tooltip="Cumulative portfolio return after subtracting all fees and simulated slippage."
          accentColor="bull"
        />

        <MetricCard
          title="CAGR (ANNUALIZED)"
          value={formatPct(currentStrat?.cagr_pct)}
          subtitle="Trading Day Convention"
          tooltip="Compound annual growth rate across simulation timeline."
          accentColor="cyan"
        />

        <MetricCard
          title="SHARPE RATIO"
          value={formatNum(currentStrat?.sharpe_ratio)}
          subtitle={data.period?.risk_free_rate !== undefined ? `Risk-Free Rate: ${(data.period.risk_free_rate * 100).toFixed(2)}%` : "Risk-Free Rate: N/A"}
          tooltip="Annualized excess return per unit of total risk."
          accentColor="default"
        />

        <MetricCard
          title="SORTINO RATIO"
          value={formatNum(currentStrat?.sortino_ratio)}
          subtitle="Downside Risk Adjusted"
          tooltip="Excess return per unit of downside semivariance."
          accentColor="default"
        />

        <MetricCard
          title="MAX DRAWDOWN"
          value={formatPct(currentStrat?.max_drawdown_pct)}
          subtitle="Peak-to-Trough Decline"
          tooltip="Worst observed portfolio drawdown during the test."
          accentColor={currentStrat?.max_drawdown_pct && currentStrat.max_drawdown_pct > 7 ? "warn" : "default"}
        />

        <MetricCard
          title="ANNUALIZED VOLATILITY"
          value={formatPct(currentStrat?.annualized_volatility_pct)}
          subtitle="Standard Deviation of Returns"
          tooltip="Annualized volatility of daily portfolio returns."
          accentColor="default"
        />

        <MetricCard
          title="TOTAL TURNOVER"
          value={currentStrat?.total_turnover !== undefined ? `${currentStrat.total_turnover.toFixed(2)}x` : "N/A"}
          subtitle={currentStrat?.trade_count !== undefined ? `${currentStrat.trade_count} Total Executions` : "N/A Executions"}
          tooltip="Ratio of total traded volume to portfolio capital."
          accentColor="default"
        />

        <MetricCard
          title="TOTAL FRICTION COSTS"
          value={formatCurrency(currentStrat?.total_costs)}
          subtitle={currentStrat?.total_fees !== undefined && currentStrat?.total_slippage !== undefined ? `Fees: ₹${currentStrat.total_fees.toFixed(0)} | Slip: ₹${currentStrat.total_slippage.toFixed(0)}` : "Fees / Slippage: N/A"}
          tooltip="Total deducted transaction fees (10 bps) and execution slippage (5 bps)."
          accentColor="default"
        />
      </div>

      {/* Equity Curve vs Benchmarks */}
      <div className="quant-card p-4 space-y-2">
        <div className="flex items-center justify-between pb-2 border-b border-quant-border">
          <div className="flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-quant-cyan" />
            <h3 className="font-mono text-xs font-bold text-quant-textPrimary">
              PORTFOLIO EQUITY TRAJECTORY VS REBALANCED BENCHMARKS
            </h3>
          </div>
          <span className="text-[11px] font-mono text-quant-textMuted">
            Zero-Lookahead Next-Open Fills
          </span>
        </div>

        <EquityCurveChart data={data.equity_curve || []} height={300} />
      </div>

      {/* Strategy Comparison Table */}
      <div className="quant-card overflow-hidden">
        <div className="p-3 bg-quant-surface border-b border-quant-border flex items-center justify-between">
          <h3 className="font-mono text-xs font-bold text-quant-textPrimary flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-quant-cyan" />
            SIDE-BY-SIDE STRATEGY & BENCHMARK COMPARISON
          </h3>
          <span className="text-[11px] font-mono text-quant-textMuted">
            Identical Timeline & Universe
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs font-mono">
            <thead className="bg-quant-surface border-b border-quant-border text-quant-textMuted text-[11px]">
              <tr>
                <th className="p-3 font-medium">STRATEGY / BENCHMARK</th>
                <th className="p-3 font-medium text-right">TOTAL RETURN</th>
                <th className="p-3 font-medium text-right">CAGR</th>
                <th className="p-3 font-medium text-right">VOLATILITY</th>
                <th className="p-3 font-medium text-right">SHARPE (6.5%)</th>
                <th className="p-3 font-medium text-right">SORTINO</th>
                <th className="p-3 font-medium text-right">MAX DD</th>
                <th className="p-3 font-medium text-right">TOTAL COSTS</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-quant-border">
              {Object.entries(data.strategies).map(([k, s]) => {
                const isSelected = k === selectedStrategy;
                return (
                  <tr
                    key={k}
                    onClick={() => setSelectedStrategy(k)}
                    className={`cursor-pointer transition-colors ${
                      isSelected ? "bg-quant-cyanMuted/30" : "hover:bg-quant-surface/60"
                    }`}
                  >
                    <td className="p-3 font-bold text-quant-textPrimary flex items-center gap-2">
                      <span className={`w-2 h-2 rounded-full ${isSelected ? "bg-quant-cyan" : "bg-quant-border"}`} />
                      {s.name}
                    </td>
                    <td className="p-3 text-right font-bold text-quant-bull">
                      {formatPct(s?.total_return_pct, true)}
                    </td>
                    <td className="p-3 text-right font-medium text-quant-textSecondary">
                      {formatPct(s?.cagr_pct)}
                    </td>
                    <td className="p-3 text-right text-quant-textSecondary">
                      {formatPct(s?.annualized_volatility_pct)}
                    </td>
                    <td className="p-3 text-right font-bold text-quant-cyan">
                      {formatNum(s?.sharpe_ratio)}
                    </td>
                    <td className="p-3 text-right text-quant-textSecondary">
                      {formatNum(s?.sortino_ratio)}
                    </td>
                    <td className="p-3 text-right text-quant-warn">
                      {formatPct(s?.max_drawdown_pct)}
                    </td>
                    <td className="p-3 text-right text-quant-textMuted">
                      {formatCurrency(s?.total_costs)}
                    </td>
                  </tr>
                );
              })}

              {/* Benchmarks Rows */}
              <tr className="bg-quant-surface/30">
                <td className="p-3 font-bold text-quant-warn flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-quant-warn" />
                  Equal Weight Rebalanced Benchmark
                </td>
                <td className="p-3 text-right font-bold text-quant-warn">
                  {formatPct(data.benchmarks?.equal_weight_return_pct, true)}
                </td>
                <td className="p-3 text-right text-quant-textMuted">N/A</td>
                <td className="p-3 text-right text-quant-textMuted">N/A</td>
                <td className="p-3 text-right text-quant-textMuted">N/A</td>
                <td className="p-3 text-right text-quant-textMuted">N/A</td>
                <td className="p-3 text-right text-quant-textMuted">N/A</td>
                <td className="p-3 text-right text-quant-textMuted">N/A</td>
              </tr>

              <tr className="bg-quant-surface/30">
                <td className="p-3 font-bold text-quant-textMuted flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-quant-muted" />
                  Buy & Hold Benchmark (5-Stock Equal)
                </td>
                <td className="p-3 text-right font-bold text-quant-textMuted">
                  {formatPct(data.benchmarks?.buy_and_hold_return_pct, true)}
                </td>
                <td className="p-3 text-right text-quant-textMuted">N/A</td>
                <td className="p-3 text-right text-quant-textMuted">N/A</td>
                <td className="p-3 text-right text-quant-textMuted">N/A</td>
                <td className="p-3 text-right text-quant-textMuted">N/A</td>
                <td className="p-3 text-right text-quant-textMuted">N/A</td>
                <td className="p-3 text-right text-quant-textMuted">N/A</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* Walk-Forward Quarterly Sub-Periods */}
      <div className="quant-card p-4">
        <h3 className="font-mono text-xs font-bold text-quant-textPrimary flex items-center gap-2 pb-3 border-b border-quant-border mb-3">
          <Calendar className="w-4 h-4 text-quant-cyan" />
          WALK-FORWARD QUARTERLY SUB-PERIOD BREAKDOWN (CONSTRAINED STRATEGY)
        </h3>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {(data.walk_forward_periods || []).map((period, idx) => (
            <div key={idx} className="bg-quant-surface p-3 rounded-lg border border-quant-border font-mono text-xs space-y-2">
              <div className="font-bold text-quant-cyan border-b border-quant-border pb-1.5">
                {period.period_id}
              </div>
              <div className="flex justify-between">
                <span className="text-quant-textMuted">Return:</span>
                <span className="font-bold text-quant-bull">{formatPct(period.return_pct, true)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-quant-textMuted">Sharpe:</span>
                <span className="font-bold text-quant-textPrimary">{formatNum(period.sharpe, 2)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-quant-textMuted">Max DD:</span>
                <span className="text-quant-warn">{formatPct(period.max_drawdown_pct)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-quant-textMuted">Friction:</span>
                <span className="text-quant-textSecondary">{period.costs !== undefined ? `₹${period.costs.toFixed(0)}` : "N/A"}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
