import React from "react";
import { Card, CardHeader, CardTitle, CardContent } from "../../components/ui/Card";
import { Table, TableHeader, TableRow, TableHead, TableBody, TableCell } from "../../components/ui/Table";
import { MOCK_INDICES, MOCK_UNIVERSE } from "../../data/mock";
import { Badge } from "../../components/ui/Badge";

export default function Market() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight text-zinc-100">Market Overview</h1>
      
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {MOCK_INDICES.map(idx => (
          <Card key={idx.name}>
            <CardContent className="p-4">
              <p className="text-xs text-quant-textSecondary uppercase tracking-wider mb-1">{idx.name}</p>
              <p className="text-xl font-mono text-zinc-100">{idx.value.toLocaleString()}</p>
              <div className="flex items-center justify-between mt-2">
                <span className={`text-sm font-mono ${idx.change >= 0 ? 'text-zinc-300' : 'text-zinc-500'}`}>
                  {idx.change > 0 ? '+' : ''}{idx.change} ({idx.changePct}%)
                </span>
                <Badge variant="outline" className="text-[10px]">{idx.status}</Badge>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader><CardTitle>Watchlist</CardTitle></CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Symbol</TableHead>
                <TableHead>Name</TableHead>
                <TableHead className="text-right">Price</TableHead>
                <TableHead className="text-right">Change</TableHead>
                <TableHead className="text-right">Volume</TableHead>
                <TableHead>Sector</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {MOCK_UNIVERSE.map(stock => (
                <TableRow key={stock.symbol}>
                  <TableCell className="font-bold text-zinc-200">{stock.symbol}</TableCell>
                  <TableCell className="text-quant-textSecondary">{stock.name}</TableCell>
                  <TableCell className="text-right font-mono">{stock.price.toFixed(2)}</TableCell>
                  <TableCell className={`text-right font-mono ${stock.change >= 0 ? 'text-zinc-300' : 'text-zinc-500'}`}>
                    {stock.change > 0 ? '+' : ''}{stock.change.toFixed(2)} ({stock.changePct}%)
                  </TableCell>
                  <TableCell className="text-right font-mono text-quant-textSecondary">{(stock.volume / 1000).toFixed(1)}k</TableCell>
                  <TableCell className="text-quant-textSecondary text-xs">{stock.sector}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
