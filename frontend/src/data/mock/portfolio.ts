export const MOCK_PORTFOLIO_SUMMARY = {
  capital: 10000000,
  invested: 8450000,
  cash: 1550000,
  exposure: 0.845,
  portfolioPnl: 245000,
  portfolioPnlPct: 0.0245,
  todayPnl: 45000,
  todayPnlPct: 0.0045,
  winRate: 0.62,
  maxDrawdown: 0.054,
  riskUtilization: 0.65,
  openPositions: 8,
};

export const MOCK_POSITIONS = [
  { symbol: "RELIANCE", side: "LONG", quantity: 500, averagePrice: 2850.00, ltp: 2985.40, currentValue: 1492700, unrealizedPnl: 67700, weight: 0.149, sector: "Energy", entryTime: "2026-08-15T10:30:00Z" },
  { symbol: "INFY", side: "LONG", quantity: 800, averagePrice: 1600.50, ltp: 1680.15, currentValue: 1344120, unrealizedPnl: 63720, weight: 0.134, sector: "Technology", entryTime: "2026-08-20T14:15:00Z" },
  { symbol: "HDFCBANK", side: "LONG", quantity: 1000, averagePrice: 1500.00, ltp: 1542.80, currentValue: 1542800, unrealizedPnl: 42800, weight: 0.154, sector: "Financials", entryTime: "2026-09-01T09:45:00Z" },
  { symbol: "LT", side: "LONG", quantity: 200, averagePrice: 3300.00, ltp: 3450.90, currentValue: 690180, unrealizedPnl: 30180, weight: 0.069, sector: "Industrials", entryTime: "2026-09-10T11:20:00Z" },
  { symbol: "ITC", side: "LONG", quantity: 2500, averagePrice: 400.00, ltp: 420.55, currentValue: 1051375, unrealizedPnl: 51375, weight: 0.105, sector: "Consumer Goods", entryTime: "2026-07-05T13:10:00Z" },
];

export const MOCK_EQUITY_CURVE = Array.from({ length: 30 }).map((_, i) => {
  const date = new Date();
  date.setDate(date.getDate() - (30 - i));
  return {
    date: date.toISOString().split('T')[0],
    value: 9500000 + (i * 15000) + (Math.random() * 100000 - 50000),
    benchmark: 9500000 + (i * 10000) + (Math.random() * 80000 - 40000)
  };
});
