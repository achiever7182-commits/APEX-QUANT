import React, { useEffect, useState } from "react";
import { Cpu, AlertTriangle, CheckCircle, Info, Database, Layers } from "lucide-react";
import { api } from "../api/client";
import { LoadingState, ErrorState } from "../components/ErrorState";
import { MetricCard } from "../components/MetricCard";
import { Tooltip } from "../components/Tooltip";
import type { MLModelMeta, ScannerItem } from "../types";

export const Strategies: React.FC = () => {
  const [model, setModel] = useState<MLModelMeta | null>(null);
  const [scanner, setScanner] = useState<ScannerItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchModel = async () => {
    try {
      setError(null);
      const [mRes, sRes] = await Promise.all([
        api.getMLModel(),
        api.getScanner().catch(() => ({ count: 0, ranked: [] })),
      ]);
      setModel(mRes);
      setScanner(sRes.ranked || []);
    } catch (err: any) {
      setError(err?.message || "Failed to load ML model telemetry.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchModel();
  }, []);

  if (loading) return <LoadingState message="Inspecting RandomForest model registry & feature definitions..." />;
  if (error && !model) return <ErrorState message={error} onRetry={fetchModel} />;

  // Calculate prediction distribution from current scanner signals
  const validPreds = scanner.filter((s) => s.predicted_return !== null && s.predicted_return !== undefined);
  const bullishCount = validPreds.filter((s) => s.predicted_return! > 0.01).length;
  const neutralCount = validPreds.filter((s) => s.predicted_return! >= -0.01 && s.predicted_return! <= 0.01).length;
  const bearishCount = validPreds.filter((s) => s.predicted_return! < -0.01).length;
  const unavailableCount = scanner.length - validPreds.length;
  const totalCount = scanner.length || 1;

  const m = model?.metrics;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-quant-border pb-3">
        <div>
          <h2 className="font-mono text-lg font-bold text-quant-textPrimary flex items-center gap-2">
            STRATEGIES & ML LAB
            <span className="text-xs font-normal text-quant-warn bg-quant-warnMuted px-2 py-0.5 rounded border border-quant-warn/30">
              RESEARCH MODEL ONLY
            </span>
          </h2>
          <p className="text-xs text-quant-textSecondary">
            Walk-forward expanding window machine learning pipeline & cross-sectional predictability evaluation.
          </p>
        </div>

        <div className="text-xs font-mono text-quant-textMuted">
          Artifact: <span className="text-quant-cyan font-semibold">{model ? `${model.model_name} ${model.version}` : "Not loaded"}</span>
        </div>
      </div>

      {/* Mandatory Honest Research Disclaimer Banner */}
      <div className="bg-quant-card border-l-4 border-quant-warn p-4 rounded-r-lg">
        <div className="flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-quant-warn shrink-0 mt-0.5" />
          <div className="text-xs leading-relaxed">
            <h4 className="font-mono font-bold text-quant-warn uppercase mb-1">
              EMPIRICAL RESEARCH EVALUATION — HISTORICAL TEST ONLY
            </h4>
            <p className="text-quant-textSecondary">
              The existing ML model has historically demonstrated <strong>weak out-of-sample predictive performance</strong>
              {m?.test_mean_ic !== undefined ? ` (Test Mean IC: ${m.test_mean_ic > 0 ? "+" : ""}${m.test_mean_ic.toFixed(4)}, Test IC IR: ${m.test_ic_ir !== undefined ? `${m.test_ic_ir > 0 ? "+" : ""}${m.test_ic_ir.toFixed(3)}` : "N/A"})` : ""}.
              Model predictions are point-in-time quantitative estimates for research and paper trading only.
              This system does <strong>not</strong> claim or imply guaranteed profitability.
            </p>
          </div>
        </div>
      </div>

      {/* Top Model Specifications */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3.5">
        <MetricCard
          title="PREDICTION TARGET"
          value={model?.target_name || "N/A"}
          subtitle="5-Day Forward Return"
          tooltip="Forward return target horizon used in expanding-window walk-forward training."
          accentColor="cyan"
        />

        <MetricCard
          title="FEATURE COUNT"
          value={model?.features?.length !== undefined ? `${model.features.length} Features` : "N/A"}
          subtitle="Step 4 Engineered Library"
          tooltip="Includes RSI, ATR, Moving Average spreads, volume ratios, and benchmark relative strength."
          accentColor="default"
        />

        <MetricCard
          title="OUT-OF-SAMPLE MEAN IC"
          value={m?.test_mean_ic !== undefined ? `${m.test_mean_ic > 0 ? "+" : ""}${m.test_mean_ic.toFixed(4)}` : "N/A"}
          subtitle="Spearman Rank Correlation"
          tooltip="Spearman correlation between predicted rankings and realized 5-day forward returns."
          accentColor="default"
        />

        <MetricCard
          title="OUT-OF-SAMPLE IC IR"
          value={m?.test_ic_ir !== undefined ? `${m.test_ic_ir > 0 ? "+" : ""}${m.test_ic_ir.toFixed(4)}` : "N/A"}
          subtitle="Information Ratio of IC"
          tooltip="Mean IC divided by standard deviation of IC across evaluation folds."
          accentColor="default"
        />
      </div>

      {/* Training & Validation Diagnostics */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Model Metrics Table */}
        <div className="quant-card p-4">
          <h3 className="font-mono text-xs font-bold text-quant-textPrimary flex items-center gap-2 pb-3 border-b border-quant-border mb-3">
            <Cpu className="w-4 h-4 text-quant-cyan" />
            MODEL PERFORMANCE & ACCURACY (POINT-IN-TIME AUDITED)
          </h3>

          <div className="space-y-2.5 font-mono text-xs">
            <div className="flex items-center justify-between p-2.5 rounded bg-quant-surface border border-quant-border">
              <span className="text-quant-textSecondary">Validation MAE:</span>
              <span className="font-bold text-quant-textPrimary">{m?.val_mae !== undefined ? (m.val_mae * 100).toFixed(2) + "%" : "N/A"}</span>
            </div>

            <div className="flex items-center justify-between p-2.5 rounded bg-quant-surface border border-quant-border">
              <span className="text-quant-textSecondary">Validation RMSE:</span>
              <span className="font-bold text-quant-textPrimary">{m?.val_rmse !== undefined ? (m.val_rmse * 100).toFixed(2) + "%" : "N/A"}</span>
            </div>

            <div className="flex items-center justify-between p-2.5 rounded bg-quant-surface border border-quant-border">
              <span className="text-quant-textSecondary">Validation Mean IC:</span>
              <span className="font-bold text-quant-bear">{m?.val_mean_ic !== undefined ? m.val_mean_ic.toFixed(4) : "N/A"}</span>
            </div>

            <div className="flex items-center justify-between p-2.5 rounded bg-quant-surface border border-quant-border">
              <span className="text-quant-textSecondary">Test MAE (Out-of-Sample):</span>
              <span className="font-bold text-quant-textPrimary">{m?.test_mae !== undefined ? (m.test_mae * 100).toFixed(2) + "%" : "N/A"}</span>
            </div>

            <div className="flex items-center justify-between p-2.5 rounded bg-quant-surface border border-quant-border">
              <span className="text-quant-textSecondary">Test RMSE (Out-of-Sample):</span>
              <span className="font-bold text-quant-textPrimary">{m?.test_rmse !== undefined ? (m.test_rmse * 100).toFixed(2) + "%" : "N/A"}</span>
            </div>

            <div className="flex items-center justify-between p-2.5 rounded bg-quant-surface border border-quant-border">
              <span className="text-quant-textSecondary">Test Mean IC (Out-of-Sample):</span>
              <span className="font-bold text-quant-bull">{m?.test_mean_ic !== undefined ? `${m.test_mean_ic > 0 ? "+" : ""}${m.test_mean_ic.toFixed(4)}` : "N/A"}</span>
            </div>
          </div>
        </div>

        {/* Prediction Distribution & Chronology */}
        <div className="quant-card p-4 space-y-4">
          <div>
            <h3 className="font-mono text-xs font-bold text-quant-textPrimary flex items-center gap-2 pb-3 border-b border-quant-border mb-3">
              <Layers className="w-4 h-4 text-quant-cyan" />
              LATEST PREDICTION SIGNAL DISTRIBUTION
            </h3>

            <div className="space-y-3 font-mono text-xs">
              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-quant-bull font-bold">BULLISH (&gt; +1.0% return):</span>
                  <span>{bullishCount} stocks ({((bullishCount / totalCount) * 100).toFixed(0)}%)</span>
                </div>
                <div className="h-2 w-full bg-quant-surface rounded-full overflow-hidden border border-quant-border">
                  <div className="h-full bg-quant-bull" style={{ width: `${(bullishCount / totalCount) * 100}%` }} />
                </div>
              </div>

              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-quant-textSecondary font-bold">NEUTRAL (±1.0% return):</span>
                  <span>{neutralCount} stocks ({((neutralCount / totalCount) * 100).toFixed(0)}%)</span>
                </div>
                <div className="h-2 w-full bg-quant-surface rounded-full overflow-hidden border border-quant-border">
                  <div className="h-full bg-quant-warn" style={{ width: `${(neutralCount / totalCount) * 100}%` }} />
                </div>
              </div>

              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-quant-bear font-bold">BEARISH (&lt; -1.0% return):</span>
                  <span>{bearishCount} stocks ({((bearishCount / totalCount) * 100).toFixed(0)}%)</span>
                </div>
                <div className="h-2 w-full bg-quant-surface rounded-full overflow-hidden border border-quant-border">
                  <div className="h-full bg-quant-bear" style={{ width: `${(bearishCount / totalCount) * 100}%` }} />
                </div>
              </div>

              {unavailableCount > 0 && (
                <div>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-quant-textMuted font-bold">PREDICTION UNAVAILABLE:</span>
                    <span>{unavailableCount} stocks ({((unavailableCount / totalCount) * 100).toFixed(0)}%)</span>
                  </div>
                  <div className="h-2 w-full bg-quant-surface rounded-full overflow-hidden border border-quant-border">
                    <div className="h-full bg-quant-textMuted" style={{ width: `${(unavailableCount / totalCount) * 100}%` }} />
                  </div>
                </div>
              )}
            </div>
          </div>

          <div className="pt-3 border-t border-quant-border text-xs font-mono space-y-1.5 text-quant-textMuted">
            <div className="flex justify-between">
              <span>Training Window:</span>
              <span className="text-quant-textPrimary">{model?.training_start?.slice(0, 10)} to {model?.training_end?.slice(0, 10)}</span>
            </div>
            <div className="flex justify-between">
              <span>Validation Window:</span>
              <span className="text-quant-textPrimary">{model?.validation_start?.slice(0, 10)} to {model?.validation_end?.slice(0, 10)}</span>
            </div>
            <div className="flex justify-between">
              <span>Out-of-Sample Test:</span>
              <span className="text-quant-textPrimary">{model?.test_start?.slice(0, 10)} to {model?.test_end?.slice(0, 10)}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Feature Catalog */}
      <div className="quant-card p-4">
        <h3 className="font-mono text-xs font-bold text-quant-textPrimary flex items-center gap-2 pb-3 border-b border-quant-border mb-3">
          <Database className="w-4 h-4 text-quant-cyan" />
          ACTIVE FEATURE CATALOG ({model?.features.length || 66} TOTAL FEATURES)
        </h3>

        <div className="flex flex-wrap gap-1.5 max-h-56 overflow-y-auto p-2 bg-quant-surface rounded border border-quant-border font-mono text-[11px]">
          {(model?.features || []).map((feat, idx) => (
            <span
              key={idx}
              className="px-2 py-0.5 rounded bg-quant-card border border-quant-border text-quant-textSecondary hover:text-quant-cyan hover:border-quant-cyan transition-colors"
            >
              {feat}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
};
