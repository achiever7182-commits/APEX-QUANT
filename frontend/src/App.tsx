import React, { useState, useEffect } from "react";
import { io } from "socket.io-client";
import { Header } from "./components/Header";
import { SafetyBanner } from "./components/SafetyBanner";
import { Navigation, type NavTab } from "./components/Navigation";
import { KillSwitchModal } from "./components/KillSwitchModal";
import { GlobalSearch } from "./components/GlobalSearch";

import { CommandCenter } from "./pages/CommandCenter";
import { Market } from "./pages/Market";
import { Scanner } from "./pages/Scanner";
import { StockDetail } from "./pages/StockDetail";
import { Portfolio } from "./pages/Portfolio";
import { Orders } from "./pages/Orders";
import { Strategies } from "./pages/Strategies";
import { Backtest } from "./pages/Backtest";
import { RiskCenter } from "./pages/RiskCenter";
import { SystemHealth } from "./pages/SystemHealth";
import { Reconciliation } from "./pages/Reconciliation";
import { Architecture } from "./pages/Architecture";
import { PaperTerminal } from "./pages/PaperTerminal";
import { LegacyBinance } from "./pages/LegacyBinance";

import { api } from "./api/client";
import type { AccountSummary, RealtimeFeedHealth, SystemHealthSummary } from "./types";

export const App: React.FC = () => {
  const [currentTab, setCurrentTab] = useState<NavTab>("command");
  const [selectedStock, setSelectedStock] = useState<string | null>(null);

  // Modals
  const [killSwitchModalOpen, setKillSwitchModalOpen] = useState(false);
  const [searchModalOpen, setSearchModalOpen] = useState(false);

  // Telemetry
  const [account, setAccount] = useState<AccountSummary | null>(null);
  const [feedHealth, setFeedHealth] = useState<RealtimeFeedHealth | null>(null);
  const [systemHealth, setSystemHealth] = useState<SystemHealthSummary | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);

  // URL route parsing on initial load and popstate
  const parsePathname = () => {
    const path = window.location.pathname.toLowerCase();
    if (path.startsWith("/stock/")) {
      const sym = path.replace("/stock/", "").toUpperCase();
      if (sym) {
        setSelectedStock(sym);
        setCurrentTab("scanner");
        return;
      }
    }
    if (path === "/market") setCurrentTab("market");
    else if (path === "/scanner") setCurrentTab("scanner");
    else if (path === "/portfolio") setCurrentTab("portfolio");
    else if (path === "/orders") setCurrentTab("orders");
    else if (path === "/strategies") setCurrentTab("strategies");
    else if (path === "/backtest") setCurrentTab("backtest");
    else if (path === "/risk") setCurrentTab("risk");
    else if (path === "/system") setCurrentTab("system");
    else if (path === "/reconciliation") setCurrentTab("reconciliation");
    else if (path === "/architecture") setCurrentTab("architecture");
    else if (path === "/paper" || path === "/paper-terminal") setCurrentTab("paper");
    else if (path === "/legacy" || path === "/legacy/binance") setCurrentTab("legacy");
    else setCurrentTab("command");
  };

  useEffect(() => {
    parsePathname();
    window.addEventListener("popstate", parsePathname);
    return () => window.removeEventListener("popstate", parsePathname);
  }, []);

  const navigateTo = (tab: NavTab, symbol?: string) => {
    if (symbol) {
      setSelectedStock(symbol);
      window.history.pushState({}, "", `/stock/${symbol}`);
    } else {
      setSelectedStock(null);
      const urlMap: Record<NavTab, string> = {
        command: "/",
        market: "/market",
        scanner: "/scanner",
        portfolio: "/portfolio",
        orders: "/orders",
        strategies: "/strategies",
        backtest: "/backtest",
        risk: "/risk",
        system: "/system",
        reconciliation: "/reconciliation",
        architecture: "/architecture",
        paper: "/paper",
        legacy: "/legacy/binance",
      };
      window.history.pushState({}, "", urlMap[tab] || "/");
    }
    setCurrentTab(tab);
    window.scrollTo(0, 0);
  };

  const refreshTelemetry = async () => {
    setIsRefreshing(true);
    try {
      const [acctRes, feedRes, sysRes] = await Promise.all([
        api.getAccountSummary().catch(() => null),
        api.getRealtimeHealth().catch(() => null),
        api.getPaperHealth().catch(() => null),
      ]);
      if (acctRes) setAccount(acctRes);
      if (feedRes) setFeedHealth(feedRes);
      if (sysRes) setSystemHealth(sysRes);
    } finally {
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    refreshTelemetry();
    const interval = setInterval(refreshTelemetry, 8000);

    // Connect to Flask Socket.IO
    const socket = io({
      transports: ["websocket", "polling"],
      reconnectionAttempts: 5,
    });

    socket.on("state_update", (data) => {
      if (data && data.price) {
        // Real-time tick received
      }
    });

    return () => {
      clearInterval(interval);
      socket.disconnect();
    };
  }, []);

  // Handle Ctrl+K shortcut for search
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setSearchModalOpen(true);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  const isKillSwitchActive = account?.kill_switch?.active ?? false;

  return (
    <div className="min-h-screen bg-quant-bg text-quant-textPrimary flex flex-col font-sans">
      {/* Top Global Safety Banner */}
      <SafetyBanner />

      {/* Persistent Application Header */}
      <Header
        systemHealth={systemHealth}
        feedHealth={feedHealth}
        killSwitchActive={isKillSwitchActive}
        onOpenKillSwitchModal={() => setKillSwitchModalOpen(true)}
        onOpenSearch={() => setSearchModalOpen(true)}
        onRefreshAll={refreshTelemetry}
        isRefreshing={isRefreshing}
      />

      {/* Primary Workstation Navigation Bar */}
      <Navigation
        currentTab={currentTab}
        onSelectTab={(tab) => navigateTo(tab)}
      />

      {/* Main View Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-4 sm:p-6">
        {selectedStock ? (
          <StockDetail
            symbol={selectedStock}
            onBack={() => {
              setSelectedStock(null);
              navigateTo("scanner");
            }}
          />
        ) : (
          <>
            {currentTab === "command" && (
              <CommandCenter onNavigate={(tab, sym) => navigateTo(tab, sym)} />
            )}

            {currentTab === "market" && (
              <Market onSelectStock={(sym) => navigateTo("scanner", sym)} />
            )}

            {currentTab === "scanner" && (
              <Scanner onSelectStock={(sym) => navigateTo("scanner", sym)} />
            )}

            {currentTab === "portfolio" && (
              <Portfolio onSelectStock={(sym) => navigateTo("scanner", sym)} />
            )}

            {currentTab === "orders" && <Orders />}

            {currentTab === "strategies" && <Strategies />}

            {currentTab === "backtest" && <Backtest />}

            {currentTab === "risk" && (
              <RiskCenter onOpenKillSwitchModal={() => setKillSwitchModalOpen(true)} />
            )}

            {currentTab === "system" && <SystemHealth />}

            {currentTab === "reconciliation" && <Reconciliation />}

            {currentTab === "architecture" && <Architecture />}

            {currentTab === "paper" && (
              <PaperTerminal
                onOpenKillSwitchModal={() => setKillSwitchModalOpen(true)}
                onSelectStock={(sym) => navigateTo("scanner", sym)}
              />
            )}

            {currentTab === "legacy" && <LegacyBinance />}
          </>
        )}
      </main>

      {/* Persistent Technical Footer */}
      <footer className="bg-quant-surface border-t border-quant-border py-3 px-6 text-xs font-mono text-quant-textMuted flex flex-col sm:flex-row items-center justify-between gap-2 mt-auto">
        <div className="flex items-center gap-2">
          <span className="font-bold text-quant-cyan">APEX-QUANT</span>
          <span>•</span>
          <span>Indian Equities Algorithmic Research Engine</span>
          <span>•</span>
          <span className="text-quant-warn">PAPER MODE ONLY</span>
        </div>

        <div className="flex items-center gap-4 text-[11px]">
          <span>Universe: NIFTY 50 Active Constituents</span>
          <span>•</span>
          <span>Zero Real Money Trading</span>
          <span>•</span>
          <span>Press <kbd className="px-1.5 py-0.5 rounded bg-quant-card border border-quant-border text-quant-cyan">Ctrl+K</kbd> to search</span>
        </div>
      </footer>

      {/* Safe Kill Switch Modal */}
      <KillSwitchModal
        isOpen={killSwitchModalOpen}
        isActive={isKillSwitchActive}
        onClose={() => setKillSwitchModalOpen(false)}
        onToggleSuccess={(newSt) => {
          if (account) {
            setAccount({
              ...account,
              kill_switch: {
                ...account.kill_switch,
                active: newSt.active,
                reason: newSt.reason,
              },
            });
          }
          refreshTelemetry();
        }}
      />

      {/* Global Symbol Search Modal */}
      <GlobalSearch
        isOpen={searchModalOpen}
        onClose={() => setSearchModalOpen(false)}
        onSelectSymbol={(sym) => navigateTo("scanner", sym)}
      />
    </div>
  );
};
export default App;
