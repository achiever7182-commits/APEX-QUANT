import React from "react";
import { Card, CardHeader, CardTitle, CardContent } from "../../components/ui/Card";
import { Table, TableHeader, TableRow, TableHead, TableBody, TableCell } from "../../components/ui/Table";
import { MOCK_SYSTEM_STATUS, MOCK_SYSTEM_HEALTH, MOCK_SYSTEM_LOGS } from "../../data/mock";
import { Badge } from "../../components/ui/Badge";

export default function System() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight text-zinc-100">System Operations</h1>
      
      <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card><CardContent className="p-4"><p className="text-xs text-quant-textSecondary uppercase mb-1">Uptime</p><p className="text-xl font-mono text-zinc-100">{MOCK_SYSTEM_HEALTH.uptime}</p></CardContent></Card>
        <Card><CardContent className="p-4"><p className="text-xs text-quant-textSecondary uppercase mb-1">Latency</p><p className="text-xl font-mono text-zinc-100">{MOCK_SYSTEM_HEALTH.latency}</p></CardContent></Card>
        <Card><CardContent className="p-4"><p className="text-xs text-quant-textSecondary uppercase mb-1">Errors (24h)</p><p className="text-xl font-mono text-zinc-100">{MOCK_SYSTEM_HEALTH.errors}</p></CardContent></Card>
        <Card><CardContent className="p-4"><p className="text-xs text-quant-textSecondary uppercase mb-1">Warnings</p><p className="text-xl font-mono text-zinc-400">{MOCK_SYSTEM_HEALTH.warnings}</p></CardContent></Card>
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-1">
          <CardHeader><CardTitle>Subsystems</CardTitle></CardHeader>
          <CardContent className="space-y-4 text-sm font-mono">
            {Object.entries(MOCK_SYSTEM_STATUS).map(([key, val]) => (
              <div key={key} className="flex justify-between items-center border-b border-zinc-800 pb-2">
                <span className="text-quant-textSecondary capitalize">{key.replace(/([A-Z])/g, ' $1').trim()}</span>
                <Badge variant="outline" className="text-[10px]">{val}</Badge>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader><CardTitle>System Logs</CardTitle></CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Timestamp</TableHead>
                  <TableHead>Level</TableHead>
                  <TableHead>Component</TableHead>
                  <TableHead>Message</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {MOCK_SYSTEM_LOGS.map((log, i) => (
                  <TableRow key={i}>
                    <TableCell className="text-quant-textSecondary text-xs font-mono w-48">{new Date(log.timestamp).toLocaleTimeString()}</TableCell>
                    <TableCell>
                      <Badge variant="outline" className={`text-[10px] ${log.level === 'WARN' ? 'border-zinc-500 text-zinc-300' : 'border-zinc-700 text-zinc-500'}`}>
                        {log.level}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-zinc-300 text-xs">{log.component}</TableCell>
                    <TableCell className="text-quant-textSecondary font-mono text-xs">{log.message}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
