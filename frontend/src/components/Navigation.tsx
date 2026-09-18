import React from "react";
import {
  LayoutDashboard,
  TrendingUp,
  Filter,
  PieChart,
  ListOrdered,
  Cpu,
  FlaskConical,
  ShieldCheck,
  Activity,
  GitCompare,
  Network,
  Terminal,
  ExternalLink,
} from "lucide-react";

export type NavTab =
  | "command"
  | "market"
  | "scanner"
  | "portfolio"
  | "orders"
  | "strategies"
  | "backtest"
  | "risk"
  | "system"
  | "reconciliation"
  | "architecture"
  | "paper"
  | "legacy";

interface NavigationProps {
  currentTab: NavTab;
  onSelectTab: (tab: NavTab) => void;
}

interface NavItem {
  id: NavTab;
  label: string;
  icon: React.ReactNode;
  badge?: string;
  isLegacy?: boolean;
}

export const Navigation: React.FC<NavigationProps> = ({ currentTab, onSelectTab }) => {
  const items: NavItem[] = [
    { id: "command", label: "COMMAND CENTER", icon: <LayoutDashboard className="w-3.5 h-3.5" /> },
    { id: "market", label: "MARKET", icon: <TrendingUp className="w-3.5 h-3.5" /> },
    { id: "scanner", label: "SCANNER", icon: <Filter className="w-3.5 h-3.5" /> },
    { id: "portfolio", label: "PORTFOLIO", icon: <PieChart className="w-3.5 h-3.5" /> },
    { id: "orders", label: "ORDERS", icon: <ListOrdered className="w-3.5 h-3.5" /> },
    { id: "strategies", label: "STRATEGIES / ML", icon: <Cpu className="w-3.5 h-3.5" /> },
    { id: "backtest", label: "BACKTEST LAB", icon: <FlaskConical className="w-3.5 h-3.5" /> },
    { id: "risk", label: "RISK CENTER", icon: <ShieldCheck className="w-3.5 h-3.5" /> },
    { id: "system", label: "SYSTEM HEALTH", icon: <Activity className="w-3.5 h-3.5" /> },
    { id: "reconciliation", label: "RECONCILIATION", icon: <GitCompare className="w-3.5 h-3.5" /> },
    { id: "architecture", label: "ARCHITECTURE", icon: <Network className="w-3.5 h-3.5" /> },
    { id: "paper", label: "PAPER TERMINAL", icon: <Terminal className="w-3.5 h-3.5" /> },
    { id: "legacy", label: "LEGACY BINANCE", icon: <ExternalLink className="w-3.5 h-3.5" />, badge: "BTC", isLegacy: true },
  ];

  return (
    <nav className="bg-quant-surface/80 border-b border-quant-border overflow-x-auto scrollbar-none px-4">
      <div className="flex items-center space-x-1 min-w-max py-1.5">
        {items.map((item) => {
          const isActive = currentTab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onSelectTab(item.id)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-mono font-medium transition-all ${
                isActive
                  ? "bg-quant-card text-quant-cyan border border-quant-borderBright shadow-sm"
                  : "text-quant-textSecondary hover:text-quant-textPrimary hover:bg-quant-card/50"
              }`}
            >
              <span className={isActive ? "text-quant-cyan" : "text-quant-textMuted"}>
                {item.icon}
              </span>
              <span>{item.label}</span>
              {item.badge && (
                <span className="text-[10px] font-mono px-1 py-0.2 rounded bg-quant-surface border border-quant-border text-quant-warn font-semibold">
                  {item.badge}
                </span>
              )}
            </button>
          );
        })}
      </div>
    </nav>
  );
};
