import React, { useState } from "react";
import { Network, ArrowDown, ChevronRight, CheckCircle2, ShieldAlert, Cpu, Database, Activity, Server, FileText } from "lucide-react";
import { StatusBadge } from "../components/StatusBadge";

interface PipelineStep {
  id: string;
  stepNumber: number;
  name: string;
  module: string;
  status: "HEALTHY" | "WARNING" | "BLOCKED";
  responsibility: string;
  input: string;
  output: string;
  invariants: string[];
}

export const Architecture: React.FC = () => {
  const [activeStepId, setActiveStepId] = useState<string>("data");

  const steps: PipelineStep[] = [
    {
      id: "data",
      stepNumber: 1,
      name: "Market Data Ingestion & Storage",
      module: "data/market/storage.py",
      status: "HEALTHY",
      responsibility: "Stores point-in-time adjusted and unadjusted daily and intraday equity bars in Apache Parquet columnar storage partitioned Hive-style by symbol.",
      input: "Exchange tick streams and historical EOD vendor data.",
      output: "Partitioned DataFrame slices (timestamp, OHLCV, adjustment_factor).",
      invariants: ["Zero-lookahead: Strict timestamp filtering (data <= T)", "Survivorship-bias protected historical reconstitution"],
    },
    {
      id: "validation",
      stepNumber: 2,
      name: "Quote Normalization & Validation",
      module: "data/realtime/validator.py",
      status: "HEALTHY",
      responsibility: "Validates quote monotonicity, bid/ask spread positivity, price reasonableness against circuits, and quote freshness.",
      input: "Raw RealtimeQuote objects from feed adapter.",
      output: "ValidatedQuote snapshots or rejection audit error.",
      invariants: ["Bid < Ask constraint", "Max staleness threshold enforcement (default 300s)"],
    },
    {
      id: "features",
      stepNumber: 3,
      name: "Feature Engineering Engine",
      module: "features/engine.py",
      status: "HEALTHY",
      responsibility: "Calculates 66 strictly point-in-time technical, momentum, volatility, and benchmark-relative indicators without lookahead leakage.",
      input: "Clean historical bar slices with warmup buffers.",
      output: "Multi-index panel DataFrame with 66 normalized features per symbol.",
      invariants: ["Feature calculations rely strictly on bars <= T", "Zero future target or price leakage"],
    },
    {
      id: "ml",
      stepNumber: 4,
      name: "Walk-Forward ML Prediction Engine",
      module: "ml/equity/",
      status: "HEALTHY",
      responsibility: "Generates point-in-time cross-sectional forward return predictions using an expanding-window RandomForest/Ridge regressor.",
      input: "Point-in-time feature panel at decision date T.",
      output: "Continuous predicted_return and confidence score per equity.",
      invariants: ["Training window strictly <= T - target_horizon (no training overlap)", "Explicit research prototype disclaimers"],
    },
    {
      id: "ranking",
      stepNumber: 5,
      name: "Cross-Sectional Opportunity Ranker",
      module: "ranking/ranker.py",
      status: "HEALTHY",
      responsibility: "Scores candidate stocks using a composite multi-factor opportunity score (ML return, RSI momentum, volatility penalty) and ranks universe 1 to N.",
      input: "ML predicted return panel and sector groupings.",
      output: "RankedUniverse containing OpportunityRank records.",
      invariants: ["Deterministic tie-breaking", "Explicit eligibility rejection reason diagnostics"],
    },
    {
      id: "portfolio",
      stepNumber: 6,
      name: "Portfolio Construction Optimizer",
      module: "portfolio/",
      status: "HEALTHY",
      responsibility: "Solves risk-constrained mean-variance SLSQP optimization to generate target asset weights and integer whole share orders.",
      input: "RankedUniverse, expected returns, and covariance matrix.",
      output: "PortfolioBuildResult with target integer shares and cash buffer.",
      invariants: ["Long-only cash equity (no shorting)", "Integer share discretization with zero negative cash"],
    },
    {
      id: "risk",
      stepNumber: 7,
      name: "12-Point Pre-Trade Risk Engine",
      module: "risk/paper_risk_manager.py",
      status: "HEALTHY",
      responsibility: "Sequentially validates 12 pre-trade risk checks before any staged order can be dispatched to the broker.",
      input: "PaperOrder, account balances, positions, and current quotes.",
      output: "RiskCheckResult (PASS or REJECT with diagnostic reason).",
      invariants: ["Persistent kill-switch check", "Max 35% single-stock, 55% sector, 100% gross exposure"],
    },
    {
      id: "ordermanager",
      stepNumber: 8,
      name: "Idempotent Order Manager",
      module: "execution/order_manager.py",
      status: "HEALTHY",
      responsibility: "Manages state transitions for paper orders from signal generation through staging, validation, submission, and fill tracking.",
      input: "Approved trade intents from risk manager.",
      output: "PaperOrder state lifecycle records.",
      invariants: ["Deterministic idempotency keys (NSE-DATE-CYCLE-SYM-SIDE)", "Zero duplicate order execution"],
    },
    {
      id: "broker",
      stepNumber: 9,
      name: "Paper Broker Sandbox",
      module: "execution/paper_broker.py",
      status: "HEALTHY",
      responsibility: "Simulates realistic market order execution with conservative friction cost assumptions (10 bps brokerage, 5 bps slippage).",
      input: "Submitted PaperOrder instances.",
      output: "PaperFill records with simulated execution prices and fees.",
      invariants: ["ZERO live broker credentials or network orders", "Integer fill quantities capped by liquidity"],
    },
    {
      id: "accounting",
      stepNumber: 10,
      name: "Double-Entry Accounting Subsystem",
      module: "execution/accounting.py",
      status: "HEALTHY",
      responsibility: "Maintains double-entry journal tracking cash debits/credits, position share balances, average cost basis, and MTM unrealized P&L.",
      input: "PaperFill transactions and latest market quotes.",
      output: "PaperAccount snapshot and PaperPosition mapping.",
      invariants: ["Cash conservation invariant", "Average cost basis preservation on partial trims"],
    },
    {
      id: "reconciliation",
      stepNumber: 11,
      name: "Tri-Party Reconciliation Engine",
      module: "execution/reconciliation.py",
      status: "HEALTHY",
      responsibility: "Performs continuous automated audit comparing local orders against broker orders, fills against accounting, and cash balances.",
      input: "Broker state, local orders, and accounting ledger.",
      output: "ReconciliationReport with clean boolean status and audit logs.",
      invariants: ["Discrepancies automatically halt automated cycle rebalancing", "Audit trail persisted to disk"],
    },
    {
      id: "persistence",
      stepNumber: 12,
      name: "Atomic State Persistence",
      module: "execution/persistence.py",
      status: "HEALTHY",
      responsibility: "Atomically writes account, position, order, and fill state to disk with backup rotation and restart recovery.",
      input: "Current in-memory paper trading state.",
      output: "data/paper/account.json, positions.json, orders.json, fills.json.",
      invariants: ["Atomic tempfile write and rename to prevent corruption on crash", "Append-only audit event log (events.jsonl)"],
    },
  ];

  const activeStep = steps.find((s) => s.id === activeStepId) || steps[0];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-quant-border pb-3">
        <div>
          <h2 className="font-mono text-lg font-bold text-quant-textPrimary flex items-center gap-2">
            SYSTEM ARCHITECTURE PIPELINE
            <span className="text-xs font-normal text-quant-cyan bg-quant-cyanMuted px-2 py-0.5 rounded border border-quant-cyan/30">
              12-STAGE PIPELINE MAP
            </span>
          </h2>
          <p className="text-xs text-quant-textSecondary">
            Interactive topological architecture mapping data ingestion through risk management, paper execution, and persistence.
          </p>
        </div>

        <div className="text-xs font-mono text-quant-textMuted flex items-center gap-2">
          <span>Click any stage to inspect design invariants & module code</span>
        </div>
      </div>

      {/* Main Grid: Pipeline Flow Diagram (Left) & Inspector (Right) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Interactive Flow Steps */}
        <div className="lg:col-span-5 space-y-2">
          {steps.map((step, idx) => {
            const isSelected = step.id === activeStepId;
            return (
              <React.Fragment key={step.id}>
                <div
                  onClick={() => setActiveStepId(step.id)}
                  className={`quant-card p-3 cursor-pointer transition-all flex items-center justify-between group ${
                    isSelected
                      ? "border-quant-cyan bg-quant-card shadow-[0_0_15px_rgba(0,212,255,0.15)]"
                      : "hover:bg-quant-surface/80"
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <div
                      className={`w-7 h-7 rounded flex items-center justify-center font-mono font-bold text-xs ${
                        isSelected
                          ? "bg-quant-cyan text-quant-bg"
                          : "bg-quant-surface text-quant-textMuted border border-quant-border"
                      }`}
                    >
                      {step.stepNumber}
                    </div>

                    <div>
                      <div className="font-mono text-xs font-bold text-quant-textPrimary group-hover:text-quant-cyan">
                        {step.name}
                      </div>
                      <div className="text-[10px] font-mono text-quant-textMuted truncate max-w-[240px]">
                        {step.module}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <StatusBadge status={step.status} size="sm" />
                    <ChevronRight className={`w-4 h-4 text-quant-textMuted transition-transform ${isSelected ? "translate-x-1 text-quant-cyan" : ""}`} />
                  </div>
                </div>

                {idx < steps.length - 1 && (
                  <div className="flex justify-center py-0.5">
                    <ArrowDown className="w-3.5 h-3.5 text-quant-borderBright" />
                  </div>
                )}
              </React.Fragment>
            );
          })}
        </div>

        {/* Right Column: Deep Module Inspector */}
        <div className="lg:col-span-7">
          <div className="quant-card p-6 sticky top-20 space-y-6">
            <div className="border-b border-quant-border pb-4">
              <div className="flex items-center justify-between mb-2">
                <span className="font-mono text-xs text-quant-cyan font-bold uppercase tracking-wider">
                  STAGE {activeStep.stepNumber} OF 12
                </span>
                <StatusBadge status={activeStep.status} size="sm" />
              </div>

              <h3 className="font-mono text-xl font-bold text-quant-textPrimary">
                {activeStep.name}
              </h3>

              <div className="mt-1.5 flex items-center gap-2 text-xs font-mono text-quant-textSecondary">
                <span>Module File:</span>
                <code className="text-quant-cyan bg-quant-surface px-2 py-0.5 rounded border border-quant-border">
                  {activeStep.module}
                </code>
              </div>
            </div>

            {/* Purpose & Responsibility */}
            <div className="space-y-2">
              <h4 className="font-mono text-xs font-bold text-quant-textSecondary uppercase tracking-wide">
                PRIMARY ARCHITECTURAL RESPONSIBILITY
              </h4>
              <p className="text-xs text-quant-textPrimary leading-relaxed bg-quant-surface p-3.5 rounded-lg border border-quant-border font-mono">
                {activeStep.responsibility}
              </p>
            </div>

            {/* Inputs & Outputs */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 font-mono text-xs">
              <div className="bg-quant-surface p-3 rounded-lg border border-quant-border">
                <span className="text-quant-textMuted block text-[10px] mb-1 font-bold">DATA CONTRACT INPUT</span>
                <span className="text-quant-textSecondary">{activeStep.input}</span>
              </div>

              <div className="bg-quant-surface p-3 rounded-lg border border-quant-border">
                <span className="text-quant-textMuted block text-[10px] mb-1 font-bold">DATA CONTRACT OUTPUT</span>
                <span className="text-quant-textSecondary">{activeStep.output}</span>
              </div>
            </div>

            {/* Mathematical & Point-in-Time Invariants */}
            <div className="space-y-2">
              <h4 className="font-mono text-xs font-bold text-quant-textSecondary uppercase tracking-wide">
                SAFETY & POINT-IN-TIME INVARIANTS
              </h4>

              <div className="space-y-2 font-mono text-xs">
                {activeStep.invariants.map((inv, i) => (
                  <div key={i} className="flex items-start gap-2 bg-quant-surface p-2.5 rounded border border-quant-border">
                    <CheckCircle2 className="w-4 h-4 text-quant-bull shrink-0 mt-0.5" />
                    <span className="text-quant-textSecondary">{inv}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
