import React from "react";
import { ShieldAlert, Info } from "lucide-react";

export const SafetyBanner: React.FC = () => {
  return (
    <div className="bg-quant-surface/95 border-b border-quant-border px-4 py-1.5 flex flex-wrap items-center justify-between text-xs text-quant-textSecondary z-40">
      <div className="flex items-center gap-2">
        <span className="flex items-center gap-1 font-semibold text-quant-warn">
          <ShieldAlert className="w-3.5 h-3.5" />
          PAPER TRADING ENVIRONMENT
        </span>
        <span className="text-quant-borderBright">|</span>
        <span className="text-quant-textMuted">Virtual Capital Execution</span>
        <span className="text-quant-borderBright">|</span>
        <span className="text-quant-bear font-mono font-medium">LIVE BROKER EXECUTION DISABLED</span>
      </div>

      <div className="flex items-center gap-3 text-[11px]">
        <span className="flex items-center gap-1 text-quant-textMuted">
          <Info className="w-3 h-3 text-quant-cyan" />
          REALTIME SOURCE: SIMULATED / CACHED
        </span>
        <span className="text-quant-borderBright">|</span>
        <span className="font-mono text-quant-textMuted">POINT-IN-TIME INVARIANTS: ENFORCED</span>
      </div>
    </div>
  );
};
