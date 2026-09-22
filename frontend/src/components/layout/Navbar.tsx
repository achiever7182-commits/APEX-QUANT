import React from "react";
import { Search, Bell, User } from "lucide-react";
import { Badge } from "../ui/Badge";
import { useDashboardData } from "../../hooks/useDashboardData";

export function Navbar({ onSearchClick }: { onSearchClick?: () => void }) {
  const { health } = useDashboardData();
  
  const isConnected = health?.connection_state === "CONNECTED";

  return (
    <header className="h-14 border-b border-quant-border bg-quant-surface/50 flex items-center justify-between px-6 flex-shrink-0">
      <div className="flex items-center gap-4 text-sm text-quant-textSecondary">
        <span className="font-medium text-zinc-300">Indian Equity Quantitative Research Platform</span>
        <span className="text-quant-borderBright">|</span>
        <Badge variant="outline" className="text-[10px] uppercase font-mono">NSE</Badge>
        <Badge variant="outline" className="text-[10px] uppercase font-mono">{health ? "Market Open" : "Waiting"}</Badge>
        <Badge variant="outline" className={`text-[10px] uppercase font-mono ${isConnected ? "bg-zinc-800 text-zinc-300" : "bg-quant-surface text-quant-textMuted border-dashed"}`}>
          {isConnected ? "Feed: Connected" : "Feed: Simulated / Offline"}
        </Badge>
      </div>

      <div className="flex items-center gap-4">
        <button onClick={onSearchClick} className="flex items-center gap-2 text-sm text-quant-textMuted bg-quant-bg border border-quant-border px-3 py-1.5 rounded-sm hover:bg-quant-surface transition-colors w-64">
          <Search className="h-4 w-4" />
          <span>Search...</span>
          <kbd className="ml-auto text-[10px] border border-quant-border px-1.5 rounded-sm bg-quant-surface">Ctrl K</kbd>
        </button>
        
        <button className="text-quant-textMuted hover:text-zinc-200 transition-colors">
          <Bell className="h-4 w-4" />
        </button>
        <button className="h-8 w-8 rounded-full bg-quant-bg border border-quant-border flex items-center justify-center text-quant-textMuted hover:text-zinc-200 transition-colors">
          <User className="h-4 w-4" />
        </button>
      </div>
    </header>
  );
}
