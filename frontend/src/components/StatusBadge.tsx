import React from "react";

interface StatusBadgeProps {
  status: string;
  size?: "sm" | "md";
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, size = "sm" }) => {
  const norm = (status || "").toUpperCase();

  let bg = "bg-quant-surface";
  let text = "text-quant-textSecondary";
  let border = "border-quant-border";
  let dot = "bg-quant-textMuted";

  if (["PASS", "FILLED", "CLEAN", "HEALTHY", "CONNECTED", "BUY", "ACTIVE", "REGULAR", "OPEN"].includes(norm)) {
    bg = "bg-quant-bullMuted";
    text = "text-quant-bull";
    border = "border-quant-bull/30";
    dot = "bg-quant-bull";
  } else if (["WARNING", "PARTIALLY_FILLED", "DEGRADED", "PRE_MARKET", "POST_MARKET", "SIMULATED", "NEUTRAL"].includes(norm)) {
    bg = "bg-quant-warnMuted";
    text = "text-quant-warn";
    border = "border-quant-warn/30";
    dot = "bg-quant-warn";
  } else if (["BLOCKED", "FAILED", "REJECTED", "DISCONNECTED", "DOWN", "SELL", "ERROR", "DISCREPANCY"].includes(norm)) {
    bg = "bg-quant-bearMuted";
    text = "text-quant-bear";
    border = "border-quant-bear/30";
    dot = "bg-quant-bear";
  } else if (["CLOSED", "WEEKEND", "HOLIDAY", "CANCELLED", "OFF"].includes(norm)) {
    bg = "bg-quant-surface";
    text = "text-quant-textMuted";
    border = "border-quant-border";
    dot = "bg-quant-textMuted";
  }

  const padding = size === "sm" ? "px-2 py-0.5 text-[11px]" : "px-2.5 py-1 text-xs";

  return (
    <span className={`inline-flex items-center gap-1.5 font-mono font-medium rounded border ${bg} ${text} ${border} ${padding}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${dot}`} />
      {status}
    </span>
  );
};
