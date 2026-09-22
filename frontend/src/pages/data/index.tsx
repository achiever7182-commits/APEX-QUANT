import React from "react";
import { Card, CardHeader, CardTitle, CardContent } from "../../components/ui/Card";
import { Badge } from "../../components/ui/Badge";

export default function DataPipeline() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight text-zinc-100">Data Pipeline Quality</h1>
      
      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
        <Card>
          <CardHeader><CardTitle>Data Feed</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <DataRow label="Connection" value="CONNECTED" status="positive" />
            <DataRow label="Latency" value="12ms" />
            <DataRow label="Provider" value="NSE (Mock)" />
            <DataRow label="Session" value="ACTIVE" status="positive" />
          </CardContent>
        </Card>
        
        <Card>
          <CardHeader><CardTitle>Data Quality</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <DataRow label="Missing Values" value="0.00%" status="positive" />
            <DataRow label="Stale Data" value="0.00%" status="positive" />
            <DataRow label="Duplicate Rows" value="0" status="positive" />
            <DataRow label="Invalid Prices" value="0" status="positive" />
          </CardContent>
        </Card>
        
        <Card>
          <CardHeader><CardTitle>Universe</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <DataRow label="Active Symbols" value="50" />
            <DataRow label="Sectors" value="12" />
            <DataRow label="Last Update" value={new Date().toISOString().split('T')[0]} />
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader><CardTitle>Pipeline Stages</CardTitle></CardHeader>
        <CardContent>
          <div className="flex justify-between items-center border-b border-zinc-800 pb-4">
            {["Market Data", "Validation", "Features", "ML Inference", "Ranking", "Risk"].map((stage, i) => (
              <div key={stage} className="flex flex-col items-center gap-2">
                <div className="h-8 w-8 rounded-full bg-zinc-200 text-zinc-900 flex items-center justify-center font-bold text-xs">{i+1}</div>
                <span className="text-xs text-quant-textSecondary font-medium">{stage}</span>
                <Badge variant="outline" className="text-[10px] border-zinc-500 text-zinc-400">OK</Badge>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function DataRow({ label, value, status }: { label: string; value: string; status?: "positive" | "negative" }) {
  return (
    <div className="flex justify-between items-center text-sm border-b border-zinc-800 pb-2 last:border-0 last:pb-0">
      <span className="text-quant-textSecondary">{label}</span>
      <span className={`font-mono ${status === 'positive' ? 'text-zinc-300' : 'text-zinc-400'}`}>{value}</span>
    </div>
  );
}
