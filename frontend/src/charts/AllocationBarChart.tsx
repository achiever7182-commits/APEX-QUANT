import React from "react";

interface AllocationItem {
  label: string;
  value: number; // in INR
  weightPct: number;
  limitPct?: number;
  sublabel?: string;
}

interface AllocationBarChartProps {
  title: string;
  items: AllocationItem[];
  maxScale?: number;
}

export const AllocationBarChart: React.FC<AllocationBarChartProps> = ({
  title,
  items,
  maxScale = 60,
}) => {
  if (!items || items.length === 0) {
    return (
      <div className="p-4 text-center font-mono text-xs text-quant-textMuted bg-quant-surface rounded border border-quant-border">
        NO ALLOCATION DATA AVAILABLE
      </div>
    );
  }

  return (
    <div className="quant-card p-4">
      <div className="flex items-center justify-between text-xs font-mono font-semibold text-quant-textSecondary mb-4">
        <span>{title}</span>
        <span className="text-[11px] text-quant-textMuted">CURRENT WEIGHT</span>
      </div>

      <div className="space-y-3.5">
        {items.map((item, idx) => {
          const isOverLimit = item.limitPct && item.weightPct > item.limitPct;
          const barColor = isOverLimit
            ? "bg-quant-bear"
            : item.weightPct > 30
            ? "bg-quant-warn"
            : "bg-quant-cyan";

          return (
            <div key={idx} className="space-y-1">
              <div className="flex items-center justify-between text-xs font-mono">
                <div className="flex items-center gap-2">
                  <span className="font-bold text-quant-textPrimary">{item.label}</span>
                  {item.sublabel && (
                    <span className="text-[10px] text-quant-textMuted">{item.sublabel}</span>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-quant-textSecondary">₹{item.value.toLocaleString("en-IN")}</span>
                  <span className={`font-bold ${isOverLimit ? "text-quant-bear" : "text-quant-textPrimary"}`}>
                    {item.weightPct.toFixed(1)}%
                  </span>
                  {item.limitPct && (
                    <span className="text-[10px] text-quant-textMuted">
                      (Cap: {item.limitPct}%)
                    </span>
                  )}
                </div>
              </div>

              {/* Progress bar container */}
              <div className="h-2 w-full bg-quant-surface rounded-full overflow-hidden relative border border-quant-border">
                {/* Limit marker line if applicable */}
                {item.limitPct && (
                  <div
                    className="absolute top-0 bottom-0 w-0.5 bg-quant-bear z-10"
                    style={{ left: `${(item.limitPct / maxScale) * 100}%` }}
                    title={`Limit Cap: ${item.limitPct}%`}
                  />
                )}
                {/* Bar */}
                <div
                  className={`h-full rounded-full transition-all duration-500 ${barColor}`}
                  style={{ width: `${Math.min(100, (item.weightPct / maxScale) * 100)}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
