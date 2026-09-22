export const MOCK_SYSTEM_STATUS = {
  bot: "ONLINE",
  executionMode: "PAPER_TRADING",
  dataFeed: "CONNECTED",
  mlModel: "READY",
  portfolioEngine: "READY",
  riskEngine: "ACTIVE",
  paperBroker: "ONLINE",
  persistence: "OK",
  dashboardApi: "ONLINE"
};

export const MOCK_SYSTEM_HEALTH = {
  uptime: "14d 08h 22m",
  latency: "42ms",
  errors: 0,
  warnings: 2,
};

export const MOCK_SYSTEM_LOGS = [
  { timestamp: new Date().toISOString(), level: "INFO", component: "DataFeed", message: "Processed 450 ticks in current cycle" },
  { timestamp: new Date(Date.now() - 60000).toISOString(), level: "INFO", component: "Orchestrator", message: "Cycle NSE-20260920_123000-V1 completed cleanly" },
  { timestamp: new Date(Date.now() - 120000).toISOString(), level: "WARN", component: "RiskEngine", message: "High volatility detected in BANK NIFTY" },
  { timestamp: new Date(Date.now() - 3600000).toISOString(), level: "INFO", component: "System", message: "Automated daily reconciliation passed" },
  { timestamp: new Date(Date.now() - 7200000).toISOString(), level: "INFO", component: "MLInference", message: "Walk-forward models successfully retrained" },
];
