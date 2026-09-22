import React from "react";
import { Card, CardHeader, CardTitle, CardContent } from "../../components/ui/Card";
import { Table, TableHeader, TableRow, TableHead, TableBody, TableCell } from "../../components/ui/Table";
import { MOCK_MODELS } from "../../data/mock";
import { Badge } from "../../components/ui/Badge";
import { Tooltip, TooltipTrigger, TooltipContent } from "../../components/ui/Tooltip";
import { Info } from "lucide-react";

export default function Models() {
  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold tracking-tight text-zinc-100">Model Registry</h1>
        <Badge variant="outline" className="font-mono bg-zinc-800">MOCK DATA</Badge>
      </div>

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Model Name</TableHead>
                <TableHead>Version</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Training Window</TableHead>
                <TableHead className="text-right">Features</TableHead>
                <TableHead>Horizon</TableHead>
                <TableHead className="text-right">Confidence</TableHead>
                <TableHead className="text-right">
                  <Tooltip>
                    <TooltipTrigger className="flex items-center gap-1 ml-auto">Val IC <Info className="h-3 w-3 text-quant-textMuted" /></TooltipTrigger>
                    <TooltipContent>
                      <p>Validation Information Coefficient.</p>
                      <p>Measures the rank correlation between predictions and actual returns.</p>
                      <p>Values &gt; 0.05 are exceptionally strong in daily equities.</p>
                    </TooltipContent>
                  </Tooltip>
                </TableHead>
                <TableHead className="text-right">Val MAE</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {MOCK_MODELS.map((model, i) => (
                <TableRow key={i}>
                  <TableCell className="font-bold text-zinc-200">{model.name}</TableCell>
                  <TableCell className="text-quant-textSecondary font-mono">{model.version}</TableCell>
                  <TableCell>
                    <Badge variant={model.status === "ACTIVE" ? "bull" : "secondary"}>
                      {model.status}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-quant-textSecondary text-xs">{model.trainingWindow}</TableCell>
                  <TableCell className="text-right font-mono text-zinc-300">{model.features}</TableCell>
                  <TableCell className="text-quant-textSecondary text-xs font-mono">{model.horizon}</TableCell>
                  <TableCell className="text-right font-mono text-zinc-300">{(model.confidence * 100).toFixed(1)}%</TableCell>
                  <TableCell className="text-right font-mono">{model.valIc.toFixed(4)}</TableCell>
                  <TableCell className="text-right font-mono">{model.valMae.toFixed(4)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
