import React from "react";
import { Card, CardHeader, CardTitle, CardContent } from "../../components/ui/Card";
import { MOCK_BACKTEST_METRICS, MOCK_TRADE_STATS } from "../../data/mock";
import { Button } from "../../components/ui/Button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "../../components/ui/Tabs";

export default function Backtests() {
  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold tracking-tight text-zinc-100">Backtest Research</h1>
        <Button variant="default">RUN BACKTEST</Button>
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-1">
          <CardHeader><CardTitle>Configuration</CardTitle></CardHeader>
          <CardContent className="space-y-4 text-sm">
            <div className="space-y-2">
              <label className="text-quant-textSecondary">Strategy</label>
              <select className="w-full bg-quant-bg border border-quant-border rounded-sm px-3 py-2 text-zinc-200">
                <option>Walk-Forward Ridge (5d)</option>
                <option>Random Forest Ensemble</option>
              </select>
            </div>
            <div className="space-y-2">
              <label className="text-quant-textSecondary">Universe</label>
              <select className="w-full bg-quant-bg border border-quant-border rounded-sm px-3 py-2 text-zinc-200">
                <option>NIFTY 50</option>
                <option>NIFTY BANK</option>
              </select>
            </div>
          </CardContent>
        </Card>

        <div className="lg:col-span-2 space-y-6">
          <Tabs defaultValue="equity" className="w-full">
            <TabsList className="mb-4">
              <TabsTrigger value="equity">Equity Curve</TabsTrigger>
              <TabsTrigger value="stats">Trade Stats</TabsTrigger>
            </TabsList>
            
            <TabsContent value="equity">
              <Card>
                <CardHeader>
                  <CardTitle className="flex justify-between items-center">
                    <span>Equity Curve</span>
                    <span className="text-[10px] bg-zinc-800 border border-zinc-700 px-2 py-1 rounded-sm text-zinc-400">MOCK DATA</span>
                  </CardTitle>
                </CardHeader>
                <CardContent className="h-64 flex items-center justify-center border-t border-zinc-800 bg-zinc-900/50">
                  <span className="text-zinc-500 font-mono text-sm">[ Equity Curve Placeholder ]</span>
                </CardContent>
              </Card>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6">
                <MetricBox title="Total Return" value={`${(MOCK_BACKTEST_METRICS.totalReturn * 100).toFixed(1)}%`} />
                <MetricBox title="CAGR" value={`${(MOCK_BACKTEST_METRICS.cagr * 100).toFixed(1)}%`} />
                <MetricBox title="Sharpe" value={MOCK_BACKTEST_METRICS.sharpe.toFixed(2)} />
                <MetricBox title="Max Drawdown" value={`${(MOCK_BACKTEST_METRICS.maxDrawdown * 100).toFixed(1)}%`} />
              </div>
            </TabsContent>

            <TabsContent value="stats">
              <Card>
                <CardHeader><CardTitle>Trade Statistics</CardTitle></CardHeader>
                <CardContent className="space-y-4">
                  <div className="flex justify-between border-b border-zinc-800 pb-2"><span className="text-quant-textSecondary">Win Rate</span><span className="font-mono text-zinc-100">{(MOCK_BACKTEST_METRICS.winRate * 100).toFixed(1)}%</span></div>
                  <div className="flex justify-between border-b border-zinc-800 pb-2"><span className="text-quant-textSecondary">Total Trades</span><span className="font-mono text-zinc-100">{MOCK_BACKTEST_METRICS.trades}</span></div>
                  <div className="flex justify-between border-b border-zinc-800 pb-2"><span className="text-quant-textSecondary">Winning Trades</span><span className="font-mono text-zinc-100">{MOCK_TRADE_STATS.winningTrades}</span></div>
                  <div className="flex justify-between border-b border-zinc-800 pb-2"><span className="text-quant-textSecondary">Losing Trades</span><span className="font-mono text-zinc-100">{MOCK_TRADE_STATS.losingTrades}</span></div>
                  <div className="flex justify-between border-b border-zinc-800 pb-2"><span className="text-quant-textSecondary">Average Win</span><span className="font-mono text-zinc-300">₹{MOCK_TRADE_STATS.averageWin.toLocaleString()}</span></div>
                  <div className="flex justify-between"><span className="text-quant-textSecondary">Average Loss</span><span className="font-mono text-zinc-500">₹{MOCK_TRADE_STATS.averageLoss.toLocaleString()}</span></div>
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        </div>
      </div>
    </div>
  );
}

function MetricBox({ title, value }: { title: string; value: string }) {
  return (
    <div className="border border-quant-border bg-quant-surface rounded-sm p-3">
      <p className="text-[10px] text-quant-textSecondary uppercase mb-1">{title}</p>
      <p className="text-lg font-mono text-zinc-200">{value}</p>
    </div>
  );
}
