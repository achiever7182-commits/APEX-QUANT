import type {
  AccountSummary,
  BacktestResults,
  Fill,
  MLModelMeta,
  OperationalTelemetry,
  Order,
  PaperPerformanceReport,
  Position,
  RealtimeFeedHealth,
  RealtimeQuote,
  ReconciliationReport,
  RiskStatus,
  ScannerItem,
  SessionRecord,
  SimulationRunConfig,
  StockDetail,
  SystemHealthSummary,
  UniverseConstituent,
} from "../types";

class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    ...options,
  });

  if (!response.ok) {
    let errorMsg = `HTTP ${response.status} ${response.statusText}`;
    try {
      const errData = await response.json();
      if (errData && errData.message) {
        errorMsg = errData.message;
      }
    } catch {
      // fallback
    }
    throw new ApiError(errorMsg, response.status);
  }

  return response.json();
}

export const api = {
  // Paper Trading & Portfolio
  getAccountSummary: () => request<AccountSummary>("/api/paper/summary"),
  getPositions: () => request<Position[]>("/api/paper/positions"),
  getOrders: () => request<Order[]>("/api/paper/orders"),
  getFills: () => request<Fill[]>("/api/paper/fills"),
  getKillSwitch: () => request<{ active: boolean; reason?: string }>("/api/paper/kill_switch"),
  toggleKillSwitch: () => request<{ active: boolean; reason?: string }>("/api/paper/kill_switch", { method: "POST" }),
  getLatestCycle: () => request<any>("/api/paper/cycle"),
  runPaperCycle: () => request<any>("/api/paper/cycle/run", { method: "POST" }),
  getReconciliation: () => request<ReconciliationReport>("/api/paper/reconciliation"),
  getPaperHealth: () => request<SystemHealthSummary>("/api/paper/health"),

  // Extended Paper Trading & Multi-Session Simulation (Step 13)
  getPaperTelemetry: () => request<OperationalTelemetry>("/api/paper/telemetry"),
  getPaperSessions: () => request<{ count: number; sessions: SessionRecord[] }>("/api/paper/sessions"),
  getPaperSessionDetail: (sessionId: string) => request<SessionRecord>(`/api/paper/sessions/${encodeURIComponent(sessionId)}`),
  runPaperSimulation: (config?: SimulationRunConfig) => request<{ status: string; sessions_count?: number; sessions?: SessionRecord[]; performance?: PaperPerformanceReport }>("/api/paper/simulation/run", { method: "POST", body: JSON.stringify(config || {}) }),
  getSimulationStatus: () => request<any>("/api/paper/simulation/status"),
  stopPaperSimulation: () => request<{ status: string }>("/api/paper/simulation/stop", { method: "POST" }),

  // Realtime Data & Market
  getQuotes: () => request<{ quotes: Record<string, RealtimeQuote>; count: number }>("/api/realtime/quotes"),
  getRealtimeHealth: () => request<RealtimeFeedHealth>("/api/realtime/health"),
  getUniverse: () => request<{ count: number; universe: UniverseConstituent[] }>("/api/market/universe"),

  // Scanner & Stock Intelligence
  getScanner: () => request<{ count: number; ranked: ScannerItem[] }>("/api/scanner"),
  getStockDetail: (symbol: string) => request<StockDetail>(`/api/stock/${encodeURIComponent(symbol)}`),

  // Research, ML & Backtest
  getMLModel: () => request<MLModelMeta>("/api/ml/model"),
  getBacktestResults: () => request<BacktestResults>("/api/backtest/results"),

  // Risk Management
  getRiskStatus: () => request<RiskStatus>("/api/risk/status"),

  // Legacy Binance Endpoints
  getLegacyState: () => request<any>("/api/state"),
  getLegacyTrades: () => request<any[]>("/api/trades"),
  getLegacyStatus: () => request<{ is_running: boolean }>("/api/bot/status"),
};
