import React from "react";
import { Card, CardHeader, CardTitle, CardContent } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";

export default function Settings() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight text-zinc-100">Settings</h1>
      
      <div className="grid lg:grid-cols-2 gap-6 max-w-4xl">
        <Card>
          <CardHeader><CardTitle>Trading Settings</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <SettingRow label="Default Universe" value="NIFTY 50" />
            <SettingRow label="Rebalance Frequency" value="Daily" />
            <SettingRow label="Transaction Costs (bps)" value="15" />
            <SettingRow label="Slippage (bps)" value="10" />
            <Button className="mt-4 w-full" variant="outline">Save Trading Settings</Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Risk Settings</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <SettingRow label="Max Position Weight" value="20%" />
            <SettingRow label="Daily Loss Limit" value="2.0%" />
            <SettingRow label="Max Drawdown" value="10.0%" />
            <Button className="mt-4 w-full" variant="outline">Save Risk Settings</Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function SettingRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col space-y-1">
      <label className="text-sm text-quant-textSecondary">{label}</label>
      <input type="text" defaultValue={value} className="bg-quant-bg border border-quant-border rounded-sm px-3 py-2 text-zinc-200 text-sm focus:outline-none focus:ring-1 focus:ring-zinc-500" />
    </div>
  );
}
