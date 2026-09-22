import React from "react";
import { Link, useLocation } from "react-router-dom";
import { 
  LayoutDashboard, 
  LineChart, 
  Activity, 
  Briefcase, 
  PieChart, 
  History, 
  Cpu, 
  Database, 
  Server, 
  Settings 
} from "lucide-react";
import { cn } from "../../utils/cn";

const NAV_ITEMS = [
  { group: "OVERVIEW", items: [
    { name: "Dashboard", path: "/dashboard", icon: LayoutDashboard }
  ]},
  { group: "MARKETS", items: [
    { name: "Market", path: "/market", icon: LineChart },
    { name: "Signals", path: "/signals", icon: Activity },
  ]},
  { group: "PORTFOLIO", items: [
    { name: "Portfolio", path: "/portfolio", icon: Briefcase },
    { name: "Positions", path: "/positions", icon: PieChart },
  ]},
  { group: "RESEARCH", items: [
    { name: "Backtests", path: "/backtests", icon: History },
    { name: "Models", path: "/models", icon: Cpu },
    { name: "Data", path: "/data", icon: Database },
  ]},
  { group: "SYSTEM", items: [
    { name: "System", path: "/system", icon: Server },
    { name: "Settings", path: "/settings", icon: Settings },
  ]}
];

export function Sidebar() {
  const location = useLocation();

  return (
    <div className="w-64 bg-quant-bg border-r border-quant-border flex flex-col h-full flex-shrink-0">
      <div className="h-14 flex items-center px-6 border-b border-quant-border">
        <span className="font-bold text-lg tracking-wider text-zinc-100">APEX-QUANT</span>
      </div>
      
      <div className="flex-1 overflow-y-auto py-4 px-3 space-y-6">
        {NAV_ITEMS.map((group) => (
          <div key={group.group}>
            <div className="px-3 mb-2 text-xs font-semibold text-quant-textMuted tracking-wider">
              {group.group}
            </div>
            <div className="space-y-1">
              {group.items.map((item) => {
                const Icon = item.icon;
                const isActive = location.pathname.startsWith(item.path) || 
                                 (location.pathname === "/" && item.path === "/dashboard");
                return (
                  <Link
                    key={item.name}
                    to={item.path}
                    className={cn(
                      "flex items-center gap-3 px-3 py-2 rounded-sm text-sm font-medium transition-colors",
                      isActive 
                        ? "bg-zinc-800 text-zinc-100" 
                        : "text-quant-textSecondary hover:bg-quant-surface hover:text-zinc-200"
                    )}
                  >
                    <Icon className="h-4 w-4" />
                    {item.name}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      <div className="p-4 border-t border-quant-border mt-auto">
        <div className="bg-zinc-900 border border-zinc-800 rounded-sm p-3 flex flex-col gap-1">
          <span className="text-xs font-bold text-zinc-100 flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-zinc-400"></span>
            PAPER TRADING
          </span>
          <span className="text-[10px] text-quant-textMuted uppercase tracking-wider">Live Execution Disabled</span>
        </div>
      </div>
    </div>
  );
}
