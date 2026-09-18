import React, { useState } from "react";

interface EquityCurvePoint {
  date: string;
  strategy: number;
  benchmark_bh: number;
  benchmark_eq: number;
}

interface EquityCurveChartProps {
  data: EquityCurvePoint[];
  height?: number;
}

export const EquityCurveChart: React.FC<EquityCurveChartProps> = ({ data, height = 280 }) => {
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  if (!data || data.length === 0) {
    return (
      <div className="h-64 flex items-center justify-center font-mono text-xs text-quant-textMuted bg-quant-surface/50 rounded border border-quant-border">
        NO EQUITY CURVE DATA AVAILABLE
      </div>
    );
  }

  const svgWidth = 800;
  const padding = { top: 20, right: 30, bottom: 30, left: 60 };
  const chartW = svgWidth - padding.left - padding.right;
  const chartH = height - padding.top - padding.bottom;

  // Extract all values
  const allVals = data.flatMap((d) => [d.strategy, d.benchmark_bh, d.benchmark_eq]);
  const minVal = Math.min(...allVals) * 0.98;
  const maxVal = Math.max(...allVals) * 1.02;
  const valRange = maxVal - minVal || 1;

  const getX = (index: number) => padding.left + (index / (data.length - 1)) * chartW;
  const getY = (val: number) => padding.top + chartH - ((val - minVal) / valRange) * chartH;

  const strategyPoints = data.map((d, i) => `${getX(i)},${getY(d.strategy)}`).join(" ");
  const bhPoints = data.map((d, i) => `${getX(i)},${getY(d.benchmark_bh)}`).join(" ");
  const eqPoints = data.map((d, i) => `${getX(i)},${getY(d.benchmark_eq)}`).join(" ");

  const areaPoints = `${getX(0)},${padding.top + chartH} ${strategyPoints} ${getX(data.length - 1)},${padding.top + chartH}`;

  const hovered = hoverIndex !== null ? data[hoverIndex] : data[data.length - 1];

  return (
    <div className="w-full flex flex-col">
      {/* Legend & Hover readout */}
      <div className="flex flex-wrap items-center justify-between text-xs font-mono py-2 px-3 bg-quant-surface border-b border-quant-border rounded-t">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5">
            <span className="w-3 h-1 bg-quant-cyan rounded-full" />
            <span className="text-quant-textSecondary">Constrained Strategy:</span>
            <strong className="text-quant-cyan">₹{hovered.strategy.toLocaleString("en-IN")}</strong>
          </div>

          <div className="flex items-center gap-1.5">
            <span className="w-3 h-1 bg-quant-warn rounded-full" />
            <span className="text-quant-textSecondary">Rebal Equal Weight:</span>
            <strong className="text-quant-warn">₹{hovered.benchmark_eq.toLocaleString("en-IN")}</strong>
          </div>

          <div className="flex items-center gap-1.5">
            <span className="w-3 h-1 bg-quant-muted rounded-full" />
            <span className="text-quant-textSecondary">Buy & Hold:</span>
            <strong className="text-quant-textMuted">₹{hovered.benchmark_bh.toLocaleString("en-IN")}</strong>
          </div>
        </div>

        <div className="text-quant-textMuted text-[11px]">
          {hovered.date}
        </div>
      </div>

      <div className="relative bg-quant-surface/40 overflow-hidden border border-quant-border border-t-0 rounded-b">
        <svg
          viewBox={`0 0 ${svgWidth} ${height}`}
          className="w-full h-auto cursor-crosshair select-none"
          onMouseLeave={() => setHoverIndex(null)}
        >
          <defs>
            <linearGradient id="strategyGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#00d4ff" stopOpacity="0.25" />
              <stop offset="100%" stopColor="#00d4ff" stopOpacity="0.0" />
            </linearGradient>
          </defs>

          {/* Grid lines */}
          {[0, 0.25, 0.5, 0.75, 1].map((ratio, idx) => {
            const y = padding.top + chartH * ratio;
            const val = maxVal - ratio * valRange;
            return (
              <g key={idx}>
                <line x1={padding.left} y1={y} x2={svgWidth - padding.right} y2={y} stroke="#1e2c48" strokeDasharray="3 3" />
                <text x={padding.left - 8} y={y + 3} fill="#64748b" fontSize={9} textAnchor="end" fontFamily="monospace">
                  ₹{(val / 100000).toFixed(1)}L
                </text>
              </g>
            );
          })}

          {/* Shaded Strategy Area */}
          <polygon points={areaPoints} fill="url(#strategyGrad)" />

          {/* Buy and Hold Line */}
          <polyline
            points={bhPoints}
            fill="none"
            stroke="#64748b"
            strokeWidth={1.5}
            strokeDasharray="4 4"
          />

          {/* Equal Weight Line */}
          <polyline
            points={eqPoints}
            fill="none"
            stroke="#f59e0b"
            strokeWidth={1.5}
            strokeDasharray="4 4"
          />

          {/* Strategy Primary Line */}
          <polyline
            points={strategyPoints}
            fill="none"
            stroke="#00d4ff"
            strokeWidth={2.5}
          />

          {/* Interactive touch targets */}
          {data.map((_, idx) => {
            const x = getX(idx);
            return (
              <rect
                key={idx}
                x={x - chartW / (data.length * 2)}
                y={padding.top}
                width={chartW / data.length}
                height={chartH}
                fill="transparent"
                onMouseEnter={() => setHoverIndex(idx)}
              />
            );
          })}

          {/* Active hover vertical crosshair */}
          {hoverIndex !== null && (
            <g>
              <line
                x1={getX(hoverIndex)}
                y1={padding.top}
                x2={getX(hoverIndex)}
                y2={padding.top + chartH}
                stroke="#00d4ff"
                strokeWidth={1}
                strokeDasharray="2 2"
              />
              <circle
                cx={getX(hoverIndex)}
                cy={getY(data[hoverIndex].strategy)}
                r={4}
                fill="#00d4ff"
                stroke="#080c14"
                strokeWidth={2}
              />
            </g>
          )}
        </svg>
      </div>
    </div>
  );
};
