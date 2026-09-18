import React from "react";
import { Tooltip } from "./Tooltip";

interface MetricCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  change?: number;
  isPositive?: boolean;
  tooltip?: string;
  icon?: React.ReactNode;
  accentColor?: "cyan" | "bull" | "bear" | "warn" | "default";
}

export const MetricCard: React.FC<MetricCardProps> = ({
  title,
  value,
  subtitle,
  change,
  isPositive,
  tooltip,
  icon,
  accentColor = "default",
}) => {
  let valueColor = "text-quant-textPrimary";
  if (accentColor === "cyan") valueColor = "text-quant-cyan";
  if (accentColor === "bull") valueColor = "text-quant-bull";
  if (accentColor === "bear") valueColor = "text-quant-bear";
  if (accentColor === "warn") valueColor = "text-quant-warn";

  return (
    <div className="quant-card p-4 flex flex-col justify-between transition-all duration-200">
      <div className="flex items-center justify-between text-xs text-quant-textSecondary mb-2">
        <span className="font-medium tracking-wide uppercase">
          {tooltip ? <Tooltip term={title} customText={tooltip} /> : title}
        </span>
        {icon && <span className="text-quant-textMuted">{icon}</span>}
      </div>

      <div className={`font-mono text-2xl font-bold tracking-tight ${valueColor}`}>
        {value}
      </div>

      {(subtitle || change !== undefined) && (
        <div className="mt-2 flex items-center gap-2 text-xs">
          {change !== undefined && (
            <span
              className={`font-mono font-medium ${
                change > 0 ? "text-quant-bull" : change < 0 ? "text-quant-bear" : "text-quant-textMuted"
              }`}
            >
              {change > 0 ? `+${change.toFixed(2)}%` : `${change.toFixed(2)}%`}
            </span>
          )}
          {subtitle && <span className="text-quant-textMuted text-[11px] truncate">{subtitle}</span>}
        </div>
      )}
    </div>
  );
};
