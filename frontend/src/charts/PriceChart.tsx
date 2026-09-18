import React, { useState } from "react";
import type { StockBar } from "../types";

interface PriceChartProps {
  bars: StockBar[];
  height?: number;
}

export const PriceChart: React.FC<PriceChartProps> = ({ bars, height = 300 }) => {
  const [hoverBar, setHoverBar] = useState<StockBar | null>(null);

  if (!bars || bars.length === 0) {
    return (
      <div className="h-64 flex items-center justify-center font-mono text-xs text-quant-textMuted bg-quant-surface/50 rounded border border-quant-border">
        NO HISTORICAL OHLCV DATA AVAILABLE
      </div>
    );
  }

  const svgWidth = 800;
  const priceHeight = height * 0.72;
  const volumeHeight = height * 0.22;
  const gap = height * 0.06;

  // Calculate min and max price
  const highs = bars.map((b) => b.high);
  const lows = bars.map((b) => b.low);
  const volumes = bars.map((b) => b.volume);

  const maxPrice = Math.max(...highs);
  const minPrice = Math.min(...lows);
  const maxVol = Math.max(...volumes);

  const priceRange = maxPrice - minPrice || 1;
  const barWidth = Math.max(2, (svgWidth / bars.length) * 0.7);
  const step = svgWidth / bars.length;

  const getY = (price: number) => {
    return priceHeight - ((price - minPrice) / priceRange) * (priceHeight - 20) - 10;
  };

  const getVolY = (vol: number) => {
    return height - (vol / (maxVol || 1)) * (volumeHeight - 10);
  };

  return (
    <div className="w-full flex flex-col">
      {/* Chart Telemetry Header */}
      <div className="flex flex-wrap items-center justify-between text-xs font-mono py-1.5 px-3 bg-quant-surface border-b border-quant-border rounded-t">
        <div className="flex items-center gap-4 text-quant-textSecondary">
          <span>
            O: <strong className="text-quant-textPrimary">₹{(hoverBar || bars[bars.length - 1]).open.toFixed(2)}</strong>
          </span>
          <span>
            H: <strong className="text-quant-bull">₹{(hoverBar || bars[bars.length - 1]).high.toFixed(2)}</strong>
          </span>
          <span>
            L: <strong className="text-quant-bear">₹{(hoverBar || bars[bars.length - 1]).low.toFixed(2)}</strong>
          </span>
          <span>
            C: <strong className="text-quant-cyan">₹{(hoverBar || bars[bars.length - 1]).close.toFixed(2)}</strong>
          </span>
          <span>
            Vol: <strong className="text-quant-textMuted">{(hoverBar || bars[bars.length - 1]).volume.toLocaleString("en-IN")}</strong>
          </span>
        </div>
        <div className="text-quant-textMuted text-[11px]">
          {(hoverBar || bars[bars.length - 1]).time}
        </div>
      </div>

      {/* SVG Canvas */}
      <div className="relative bg-quant-surface/40 overflow-hidden border border-quant-border border-t-0 rounded-b">
        <svg
          viewBox={`0 0 ${svgWidth} ${height}`}
          className="w-full h-auto cursor-crosshair select-none"
          onMouseLeave={() => setHoverBar(null)}
        >
          {/* Horizontal grid lines */}
          {[0.2, 0.4, 0.6, 0.8].map((ratio, idx) => {
            const y = priceHeight * ratio;
            const p = maxPrice - ratio * priceRange;
            return (
              <g key={idx}>
                <line x1={0} y1={y} x2={svgWidth} y2={y} stroke="#1e2c48" strokeDasharray="3 3" />
                <text x={svgWidth - 5} y={y - 3} fill="#64748b" fontSize={9} textAnchor="end" fontFamily="monospace">
                  ₹{p.toFixed(1)}
                </text>
              </g>
            );
          })}

          {/* Volume separator */}
          <line
            x1={0}
            y1={priceHeight + gap / 2}
            x2={svgWidth}
            y2={priceHeight + gap / 2}
            stroke="#1e2c48"
          />

          {/* Candlesticks and Volume Bars */}
          {bars.map((bar, i) => {
            const x = i * step + step / 2;
            const isBull = bar.close >= bar.open;
            const color = isBull ? "#10b981" : "#f43f5e";
            const candleTop = Math.min(getY(bar.open), getY(bar.close));
            const candleHeight = Math.max(1.5, Math.abs(getY(bar.open) - getY(bar.close)));
            const volY = getVolY(bar.volume);

            return (
              <g
                key={i}
                onMouseEnter={() => setHoverBar(bar)}
                className="transition-opacity hover:opacity-100"
              >
                {/* High-Low Wick */}
                <line
                  x1={x}
                  y1={getY(bar.high)}
                  x2={x}
                  y2={getY(bar.low)}
                  stroke={color}
                  strokeWidth={1}
                />

                {/* Real Body */}
                <rect
                  x={x - barWidth / 2}
                  y={candleTop}
                  width={barWidth}
                  height={candleHeight}
                  fill={color}
                  rx={0.5}
                />

                {/* Volume Bar */}
                <rect
                  x={x - barWidth / 2}
                  y={volY}
                  width={barWidth}
                  height={height - volY}
                  fill={color}
                  opacity={0.35}
                />
              </g>
            );
          })}
        </svg>
      </div>
    </div>
  );
};
