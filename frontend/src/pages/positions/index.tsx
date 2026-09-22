import React from "react";
import { Card, CardContent } from "../../components/ui/Card";
import { Table, TableHeader, TableRow, TableHead, TableBody, TableCell } from "../../components/ui/Table";
import { MOCK_POSITIONS } from "../../data/mock";

export default function Positions() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight text-zinc-100">Open Positions</h1>
      
      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Symbol</TableHead>
                <TableHead>Side</TableHead>
                <TableHead className="text-right">Quantity</TableHead>
                <TableHead className="text-right">Avg Price</TableHead>
                <TableHead className="text-right">LTP</TableHead>
                <TableHead className="text-right">Current Value</TableHead>
                <TableHead className="text-right">Unrealized P&L</TableHead>
                <TableHead className="text-right">Weight</TableHead>
                <TableHead>Entry Time</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {MOCK_POSITIONS.map((pos, i) => (
                <TableRow key={i}>
                  <TableCell className="font-bold text-zinc-200">{pos.symbol}</TableCell>
                  <TableCell><span className="text-xs border border-zinc-700 bg-zinc-900 px-1.5 py-0.5 rounded-sm">{pos.side}</span></TableCell>
                  <TableCell className="text-right font-mono">{pos.quantity}</TableCell>
                  <TableCell className="text-right font-mono">{pos.averagePrice.toFixed(2)}</TableCell>
                  <TableCell className="text-right font-mono">{pos.ltp.toFixed(2)}</TableCell>
                  <TableCell className="text-right font-mono">₹{pos.currentValue.toLocaleString()}</TableCell>
                  <TableCell className={`text-right font-mono ${pos.unrealizedPnl >= 0 ? 'text-zinc-300' : 'text-zinc-500'}`}>
                    {pos.unrealizedPnl > 0 ? '+' : ''}₹{pos.unrealizedPnl.toLocaleString()}
                  </TableCell>
                  <TableCell className="text-right font-mono text-quant-textSecondary">{(pos.weight * 100).toFixed(1)}%</TableCell>
                  <TableCell className="text-quant-textSecondary text-xs">{new Date(pos.entryTime).toLocaleString()}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
