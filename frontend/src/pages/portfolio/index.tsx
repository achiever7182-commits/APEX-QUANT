import React from "react";
import { Card, CardHeader, CardTitle, CardContent } from "../../components/ui/Card";
import { useDashboardData } from "../../hooks/useDashboardData";
import { PieChart, Pie, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";

export default function Portfolio() {
  const { summary, positions, loading } = useDashboardData();

  const totalEquity = summary?.total_equity || 0;
  const invested = summary?.positions_value || 0;
  const cash = summary?.cash || 0;
  const unrealizedPnl = summary?.unrealized_pnl || 0;

  const hasPositions = positions && positions.length > 0;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight text-zinc-100">Portfolio Overview</h1>
      
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card><CardContent className="p-4"><p className="text-xs text-quant-textSecondary uppercase mb-1">Total Equity</p><p className="text-xl font-mono text-zinc-100">{loading ? "..." : `₹${totalEquity.toLocaleString()}`}</p></CardContent></Card>
        <Card><CardContent className="p-4"><p className="text-xs text-quant-textSecondary uppercase mb-1">Invested</p><p className="text-xl font-mono text-zinc-300">{loading ? "..." : `₹${invested.toLocaleString()}`}</p></CardContent></Card>
        <Card><CardContent className="p-4"><p className="text-xs text-quant-textSecondary uppercase mb-1">Cash</p><p className="text-xl font-mono text-zinc-300">{loading ? "..." : `₹${cash.toLocaleString()}`}</p></CardContent></Card>
        <Card><CardContent className="p-4"><p className="text-xs text-quant-textSecondary uppercase mb-1">Unrealized P&L</p><p className="text-xl font-mono text-zinc-100">{loading ? "..." : `₹${unrealizedPnl.toLocaleString()}`}</p></CardContent></Card>
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader><CardTitle>Allocation by Sector</CardTitle></CardHeader>
          <CardContent className="h-64 border-t border-zinc-800 bg-quant-surface/30 p-4 relative">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                {/* Real data would map here */}
                <Pie data={[]} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80} fill="#52525b" />
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
            {!hasPositions && (
              <div className="absolute inset-0 flex items-center justify-center">
                <span className="text-zinc-500 font-mono text-sm border border-dashed border-zinc-700 bg-quant-bg px-4 py-2 rounded-sm uppercase tracking-wider">NO OPEN POSITIONS</span>
              </div>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Portfolio Concentration</CardTitle></CardHeader>
          <CardContent className="h-64 border-t border-zinc-800 bg-quant-surface/30 p-4 relative">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={[]}>
                <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
                <XAxis dataKey="name" stroke="#52525b" fontSize={10} tickLine={false} axisLine={false} />
                <YAxis stroke="#52525b" fontSize={10} tickLine={false} axisLine={false} />
                <Tooltip />
                <Bar dataKey="value" fill="#3f3f46" />
              </BarChart>
            </ResponsiveContainer>
            {!hasPositions && (
              <div className="absolute inset-0 flex items-center justify-center">
                <span className="text-zinc-500 font-mono text-sm border border-dashed border-zinc-700 bg-quant-bg px-4 py-2 rounded-sm uppercase tracking-wider">NO OPEN POSITIONS</span>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
