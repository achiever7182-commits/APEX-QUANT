import { MOCK_UNIVERSE } from "./market";

export const MOCK_SIGNALS = [
  { symbol: "ICICIBANK", price: 1105.35, signal: "BUY", confidence: 0.85, strategy: "Walk-Forward Ridge (5d)", expectedReturn: 0.045, entry: 1105.00, stopLoss: 1080.00, target: 1150.00, risk: "Low", timestamp: new Date().toISOString() },
  { symbol: "LT", price: 3450.90, signal: "BUY", confidence: 0.78, strategy: "Walk-Forward Ridge (5d)", expectedReturn: 0.038, entry: 3450.00, stopLoss: 3380.00, target: 3600.00, risk: "Medium", timestamp: new Date(Date.now() - 50000).toISOString() },
  { symbol: "TCS", price: 4120.75, signal: "SELL", confidence: 0.92, strategy: "Walk-Forward Ridge (5d)", expectedReturn: -0.052, entry: 4120.00, stopLoss: 4200.00, target: 3900.00, risk: "Medium", timestamp: new Date(Date.now() - 120000).toISOString() },
  { symbol: "SBIN", price: 765.20, signal: "SELL", confidence: 0.65, strategy: "Walk-Forward Ridge (5d)", expectedReturn: -0.021, entry: 765.00, stopLoss: 780.00, target: 740.00, risk: "High", timestamp: new Date(Date.now() - 300000).toISOString() },
  { symbol: "RELIANCE", price: 2985.40, signal: "HOLD", confidence: 0.45, strategy: "Walk-Forward Ridge (5d)", expectedReturn: 0.005, entry: 2985.00, stopLoss: 2900.00, target: 3100.00, risk: "Low", timestamp: new Date(Date.now() - 600000).toISOString() },
];

export const MOCK_RECENT_ACTIVITY = [
  { id: "1", type: "SIGNAL_GENERATED", message: "BUY signal generated for ICICIBANK", timestamp: new Date().toISOString() },
  { id: "2", type: "RISK_APPROVED", message: "Risk gate approved order for LT", timestamp: new Date(Date.now() - 45000).toISOString() },
  { id: "3", type: "ORDER_SIMULATED", message: "Simulated BUY order for LT (100 shares)", timestamp: new Date(Date.now() - 48000).toISOString() },
  { id: "4", type: "PORTFOLIO_REBALANCE", message: "Target portfolio weights updated", timestamp: new Date(Date.now() - 120000).toISOString() },
  { id: "5", type: "DATA_FEED", message: "NSE market feed heartbeat OK", timestamp: new Date(Date.now() - 300000).toISOString() },
];
