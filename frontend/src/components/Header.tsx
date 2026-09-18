import React, { useState, useEffect } from "react";
import { Activity, Power, Search, Shield, Zap, Layers, RefreshCw } from "lucide-react";
import { StatusBadge } from "./StatusBadge";
import type { RealtimeFeedHealth, SystemHealthSummary } from "../types";

interface HeaderProps {
  systemHealth?: SystemHealthSummary | null;
  feedHealth?: RealtimeFeedHealth | null;
  killSwitchActive: boolean;
  onOpenKillSwitchModal: () => void;
  onOpenSearch: () => void;
  onRefreshAll?: () => void;
  isRefreshing?: boolean;
}

export const Header: React.FC<HeaderProps> = ({
  systemHealth,
  feedHealth,
  killSwitchActive,
  onOpenKillSwitchModal,
  onOpenSearch,
  onRefreshAll,
  isRefreshing,
}) => {
  const [currentTime, setCurrentTime] = useState<string>("");

  useEffect(() => {
    const update = () => {
      const now = new Date();
      // Format IST time
      setCurrentTime(
        now.toLocaleTimeString("en-IN", {
          timeZone: "Asia/Kolkata",
          hour12: false,
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
        }) + " IST"
      );
    };
    update();
    const interval = setInterval(update, 1000);
    return () => clearInterval(interval);
  }, []);

  const marketSession = feedHealth?.market_session || systemHealth?.market_session || "REGULAR";
  const isFeedHealthy = feedHealth?.status === "HEALTHY" || !feedHealth;

  return (
    <header className="bg-quant-surface border-b border-quant-border sticky top-0 z-30 px-4 py-2.5">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
        {/* Brand & Tagline */}
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-quant-card border border-quant-cyan flex items-center justify-center shadow-[0_0_12px_rgba(0,212,255,0.25)]">
            <span className="font-mono font-black text-sm text-quant-cyan tracking-wider">AQ</span>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="font-mono font-extrabold text-base tracking-wider text-quant-textPrimary flex items-center gap-1.5">
                APEX<span className="text-quant-cyan">QUANT</span>
              </h1>
              <span className="text-[10px] font-mono font-bold px-1.5 py-0.5 rounded bg-quant-card border border-quant-border text-quant-cyan tracking-wide">
                PAPER V1.0
              </span>
            </div>
            <p className="text-[10px] tracking-widest uppercase font-semibold text-quant-textMuted">
              Quantitative Equity Intelligence Platform
            </p>
          </div>
        </div>

        {/* Real-time Status Badges */}
        <div className="flex flex-wrap items-center gap-2 sm:gap-3 text-xs">
          {/* Market Session */}
          <div className="flex items-center gap-1.5 bg-quant-card border border-quant-border px-2.5 py-1 rounded-md">
            <span className="text-[11px] text-quant-textMuted font-mono">MARKET:</span>
            <StatusBadge status={marketSession} size="sm" />
          </div>

          {/* Data Feed */}
          <div className="flex items-center gap-1.5 bg-quant-card border border-quant-border px-2.5 py-1 rounded-md">
            <span className="text-[11px] text-quant-textMuted font-mono">FEED:</span>
            <span className="inline-flex items-center gap-1 text-[11px] font-mono text-quant-cyan font-medium">
              <span className="w-1.5 h-1.5 rounded-full bg-quant-cyan animate-pulse-cyan" />
              SIMULATED RT
            </span>
          </div>

          {/* System Health */}
          <div className="flex items-center gap-1.5 bg-quant-card border border-quant-border px-2.5 py-1 rounded-md">
            <span className="text-[11px] text-quant-textMuted font-mono">HEALTH:</span>
            <StatusBadge status={killSwitchActive ? "BLOCKED" : "HEALTHY"} size="sm" />
          </div>

          {/* Kill Switch Toggle Button */}
          <button
            onClick={onOpenKillSwitchModal}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md font-mono text-xs font-semibold border transition-all ${
              killSwitchActive
                ? "bg-quant-bear text-white border-quant-bear hover:bg-quant-bear/90 animate-pulse"
                : "bg-quant-card text-quant-textSecondary border-quant-border hover:border-quant-warn hover:text-quant-warn"
            }`}
            title="Toggle Paper Trading Kill Switch"
          >
            <Power className="w-3.5 h-3.5" />
            <span>{killSwitchActive ? "KILL SWITCH ENGAGED" : "KILL SWITCH: ARMED"}</span>
          </button>

          {/* Search Trigger */}
          <button
            onClick={onOpenSearch}
            className="flex items-center gap-1.5 bg-quant-card hover:bg-quant-elevated border border-quant-border hover:border-quant-borderBright px-2.5 py-1 rounded-md text-quant-textSecondary hover:text-quant-textPrimary text-xs transition-colors"
            title="Global Stock Search"
          >
            <Search className="w-3.5 h-3.5 text-quant-cyan" />
            <span className="hidden lg:inline text-[11px] text-quant-textMuted font-mono">Search (50)</span>
          </button>

          {/* Manual Refresh */}
          {onRefreshAll && (
            <button
              onClick={onRefreshAll}
              disabled={isRefreshing}
              className="p-1.5 bg-quant-card hover:bg-quant-elevated border border-quant-border rounded-md text-quant-textSecondary hover:text-quant-cyan transition-colors"
              title="Refresh telemetry"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? "animate-spin text-quant-cyan" : ""}`} />
            </button>
          )}

          {/* IST Live Clock */}
          <div className="font-mono text-xs text-quant-textSecondary px-2 py-1 bg-quant-card border border-quant-border rounded-md hidden xl:block">
            {currentTime}
          </div>
        </div>
      </div>
    </header>
  );
};
