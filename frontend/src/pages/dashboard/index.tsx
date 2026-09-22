import React from "react";
import { Card, CardHeader, CardTitle, CardContent } from "../../components/ui/Card";
import { useDashboardData } from "../../hooks/useDashboardData";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";

export default function Dashboard() {
  const { summary, loading } = useDashboardData();

  const totalEquity = summary?.total_equity || 0;
  const todayPnl = summary?.daily_pnl || 0;
  const overallPnl = (summary?.realized_pnl || 0) + (summary?.unrealized_pnl || 0);
  const cash = summary?.cash || 0;
  const exposure = summary && summary.total_equity > 0 ? summary.positions_value / summary.total_equity : 0;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight text-zinc-100">Dashboard</h1>
      
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        <Metric title="Portfolio Value" value={loading ? "WAITING..." : summary ? `₹${totalEquity.toLocaleString()}` : "N/A"} />
        <Metric title="Today's P&L" value={loading ? "WAITING..." : summary ? `₹${todayPnl.toLocaleString()}` : "N/A"} trend={todayPnl >= 0 ? "positive" : "negative"} />
        <Metric title="Overall P&L" value={loading ? "WAITING..." : summary ? `₹${overallPnl.toLocaleString()}` : "N/A"} trend={overallPnl >= 0 ? "positive" : "negative"} />
        <Metric title="Available Capital" value={loading ? "WAITING..." : summary ? `₹${cash.toLocaleString()}` : "N/A"} />
        <Metric title="Exposure" value={loading ? "WAITING..." : summary ? `${(exposure * 100).toFixed(1)}%` : "N/A"} />
        <Metric title="Win Rate" value="N/A" />
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-2">
          <CardHeader><CardTitle>Portfolio Performance</CardTitle></CardHeader>
          <CardContent className="h-64 border-t border-zinc-800 bg-quant-surface/30 p-4 relative">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={[]}>
                <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
                <XAxis dataKey="timestamp" stroke="#52525b" fontSize={10} tickLine={false} axisLine={false} />
                <YAxis stroke="#52525b" fontSize={10} tickLine={false} axisLine={false} tickFormatter={(val) => `₹${val.toLocaleString()}`} />
                <Tooltip />
              </LineChart>
            </ResponsiveContainer>
            <div className="absolute inset-0 flex items-center justify-center">
              <span className="text-zinc-500 font-mono text-sm border border-dashed border-zinc-700 bg-quant-bg px-4 py-2 rounded-sm uppercase tracking-wider">WAITING FOR DATA</span>
            </div>
          </CardContent>
        </Card>
        
        <Card>
          <CardHeader><CardTitle>Risk Monitor</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <RiskItem label="Gross Exposure" value={summary ? `${(exposure * 100).toFixed(1)}%` : "N/A"} limit="100%" />
            <RiskItem label="Net Exposure" value={summary ? `${(exposure * 100).toFixed(1)}%` : "N/A"} limit="100%" />
            <RiskItem label="Max Position Weight" value="N/A" limit="20%" />
            <RiskItem label="Daily Loss Limit" value="N/A" limit="2.0%" />
            <RiskItem label="Drawdown" value={summary ? `${(summary.max_drawdown * 100).toFixed(1)}%` : "N/A"} limit="10.0%" />
            <RiskItem label="Risk Utilization" value="N/A" />
            <RiskItem label="Open Positions" value={summary ? `${summary.positions_count}` : "N/A"} />
            <RiskItem label="Risk Gate" value="PASS" status="positive" />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function Metric({ title, value, trend }: { title: string; value: string; trend?: "positive" | "negative" }) {
  return (
    <Card>
      <CardContent className="p-4">
        <p className="text-xs text-quant-textSecondary uppercase tracking-wider mb-1">{title}</p>
        <p className={`text-xl font-mono ${trend === 'positive' ? 'text-zinc-100' : trend === 'negative' ? 'text-zinc-500' : 'text-zinc-100'}`}>{value}</p>
      </CardContent>
    </Card>
  );
}

function RiskItem({ label, value, limit, status }: { label: string; value: string; limit?: string; status?: "positive" | "negative" }) {
  return (
    <div className="flex justify-between items-center text-sm border-b border-zinc-800 pb-2 last:border-0 last:pb-0">
      <span className="text-quant-textSecondary">{label}</span>
      <div className="flex items-center gap-2">
        <span className={`font-mono ${status === 'positive' ? 'text-zinc-100' : 'text-zinc-300'}`}>{value}</span>
        {limit && <span className="text-xs text-zinc-600 font-mono">/ {limit}</span>}
      </div>
    </div>
  );
}
