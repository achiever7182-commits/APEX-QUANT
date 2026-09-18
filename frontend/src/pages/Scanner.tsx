import React, { useEffect, useState } from "react";
import { Search, Filter, ArrowUpDown, TrendingUp, ShieldAlert, Sparkles } from "lucide-react";
import { api } from "../api/client";
import { LoadingState, ErrorState, EmptyState } from "../components/ErrorState";
import { StatusBadge } from "../components/StatusBadge";
import type { ScannerItem } from "../types";

interface ScannerProps {
  onSelectStock: (symbol: string) => void;
}

export const Scanner: React.FC<ScannerProps> = ({ onSelectStock }) => {
  const [items, setItems] = useState<ScannerItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [search, setSearch] = useState("");
  const [selectedSector, setSelectedSector] = useState("ALL");
  const [sentimentFilter, setSentimentFilter] = useState<"ALL" | "BULLISH" | "NEUTRAL" | "BEARISH">("ALL");
  const [riskFilter, setRiskFilter] = useState<"ALL" | "PASS" | "WARNING" | "BLOCKED">("ALL");
  const [minScore, setMinScore] = useState<number>(0);

  // Sorting
  const [sortField, setSortField] = useState<"rank" | "score" | "return" | "volatility">("rank");
  const [sortAsc, setSortAsc] = useState(true);

  const fetchScanner = async () => {
    try {
      setError(null);
      const res = await api.getScanner();
      setItems(res.ranked || []);
    } catch (err: any) {
      setError(err?.message || "Failed to load cross-sectional stock scanner.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchScanner();
    const interval = setInterval(fetchScanner, 15000); // 15s refresh
    return () => clearInterval(interval);
  }, []);

  if (loading) return <LoadingState message="Executing Cross-Sectional Ranking & ML Signal Screening..." />;
  if (error && items.length === 0) return <ErrorState message={error} onRetry={fetchScanner} />;

  const sectors = ["ALL", ...Array.from(new Set(items.map((i) => i.sector || "General"))).sort()];

  // Filtering
  const filtered = items.filter((item) => {
    const matchesSearch =
      item.symbol.toLowerCase().includes(search.toLowerCase().trim()) ||
      item.company_name.toLowerCase().includes(search.toLowerCase().trim());

    const matchesSector = selectedSector === "ALL" || item.sector === selectedSector;

    const matchesRisk = riskFilter === "ALL" || item.risk_status === riskFilter;

    const matchesScore = minScore === 0 ? true : (item.quant_score !== null && item.quant_score >= minScore);

    let matchesSentiment = true;
    if (sentimentFilter === "BULLISH") matchesSentiment = item.predicted_return !== null && item.predicted_return > 0.01;
    else if (sentimentFilter === "NEUTRAL") matchesSentiment = item.predicted_return !== null && item.predicted_return >= -0.01 && item.predicted_return <= 0.01;
    else if (sentimentFilter === "BEARISH") matchesSentiment = item.predicted_return !== null && item.predicted_return < -0.01;

    return matchesSearch && matchesSector && matchesRisk && matchesScore && matchesSentiment;
  });

  // Sorting
  filtered.sort((a, b) => {
    let comparison = 0;
    if (sortField === "rank") comparison = a.rank - b.rank;
    if (sortField === "score") {
      const aScore = a.quant_score ?? -999;
      const bScore = b.quant_score ?? -999;
      comparison = aScore - bScore;
    }
    if (sortField === "return") {
      const aRet = a.predicted_return ?? -999;
      const bRet = b.predicted_return ?? -999;
      comparison = aRet - bRet;
    }
    if (sortField === "volatility") comparison = a.volatility_20d - b.volatility_20d;

    // For score & return, default descending if sortAsc is true
    if (sortField === "score" || sortField === "return") {
      return sortAsc ? -comparison : comparison;
    }
    return sortAsc ? comparison : -comparison;
  });

  const toggleSort = (field: typeof sortField) => {
    if (sortField === field) setSortAsc(!sortAsc);
    else {
      setSortField(field);
      setSortAsc(true);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-quant-border pb-3">
        <div>
          <h2 className="font-mono text-lg font-bold text-quant-textPrimary flex items-center gap-2">
            STOCK SCANNER
            <span className="text-xs font-normal text-quant-cyan bg-quant-cyanMuted px-2 py-0.5 rounded border border-quant-cyan/30">
              CROSS-SECTIONAL RANKING
            </span>
          </h2>
          <p className="text-xs text-quant-textSecondary">
            Quantitative screening engine scoring momentum, relative strength, volatility, and forward return predictions.
          </p>
        </div>

        <div className="text-xs font-mono text-quant-textMuted">
          Target Horizon: <span className="text-quant-cyan font-bold">5-Day Forward Return</span>
        </div>
      </div>

      {/* Control Bar: Filters, Search, and Thresholds */}
      <div className="quant-card p-4 space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          {/* Search */}
          <div className="relative flex-1 min-w-[200px]">
            <Search className="w-4 h-4 text-quant-textMuted absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search symbol or company..."
              className="w-full pl-9 pr-3 py-1.5 bg-quant-surface border border-quant-border rounded text-xs font-mono text-quant-textPrimary placeholder:text-quant-textMuted focus:outline-none focus:border-quant-cyan"
            />
          </div>

          {/* Sector Filter */}
          <div className="flex items-center gap-1.5 text-xs font-mono">
            <span className="text-quant-textMuted">SECTOR:</span>
            <select
              value={selectedSector}
              onChange={(e) => setSelectedSector(e.target.value)}
              className="bg-quant-surface border border-quant-border rounded px-2.5 py-1.5 text-xs font-mono text-quant-textPrimary focus:outline-none focus:border-quant-cyan"
            >
              {sectors.map((sec) => (
                <option key={sec} value={sec}>
                  {sec}
                </option>
              ))}
            </select>
          </div>

          {/* Sentiment Filter */}
          <div className="flex items-center gap-1.5 text-xs font-mono">
            <span className="text-quant-textMuted">OUTLOOK:</span>
            <select
              value={sentimentFilter}
              onChange={(e) => setSentimentFilter(e.target.value as any)}
              className="bg-quant-surface border border-quant-border rounded px-2.5 py-1.5 text-xs font-mono text-quant-textPrimary focus:outline-none focus:border-quant-cyan"
            >
              <option value="ALL">ALL SIGNALS</option>
              <option value="BULLISH">BULLISH (&gt;+1%)</option>
              <option value="NEUTRAL">NEUTRAL (±1%)</option>
              <option value="BEARISH">BEARISH (&lt;-1%)</option>
            </select>
          </div>

          {/* Risk Filter */}
          <div className="flex items-center gap-1.5 text-xs font-mono">
            <span className="text-quant-textMuted">RISK:</span>
            <select
              value={riskFilter}
              onChange={(e) => setRiskFilter(e.target.value as any)}
              className="bg-quant-surface border border-quant-border rounded px-2.5 py-1.5 text-xs font-mono text-quant-textPrimary focus:outline-none focus:border-quant-cyan"
            >
              <option value="ALL">ALL RISKS</option>
              <option value="PASS">PASS ONLY</option>
              <option value="WARNING">WARNING</option>
              <option value="BLOCKED">BLOCKED</option>
            </select>
          </div>

          {/* Min Score Slider */}
          <div className="flex items-center gap-2 text-xs font-mono">
            <span className="text-quant-textMuted">MIN SCORE:</span>
            <input
              type="range"
              min={0}
              max={80}
              step={5}
              value={minScore}
              onChange={(e) => setMinScore(Number(e.target.value))}
              className="w-24 accent-quant-cyan cursor-pointer"
            />
            <span className="font-bold text-quant-cyan min-w-[24px]">{minScore}</span>
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="quant-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs font-mono">
            <thead className="bg-quant-surface border-b border-quant-border text-quant-textMuted text-[11px]">
              <tr>
                <th
                  onClick={() => toggleSort("rank")}
                  className="p-3 font-medium cursor-pointer hover:text-quant-textPrimary"
                >
                  <span className="flex items-center gap-1">
                    RANK <ArrowUpDown className="w-3 h-3" />
                  </span>
                </th>
                <th className="p-3 font-medium">SYMBOL</th>
                <th className="p-3 font-medium text-right">PRICE</th>
                <th
                  onClick={() => toggleSort("score")}
                  className="p-3 font-medium text-right cursor-pointer hover:text-quant-textPrimary"
                >
                  <span className="flex items-center justify-end gap-1">
                    QUANT SCORE <ArrowUpDown className="w-3 h-3" />
                  </span>
                </th>
                <th
                  onClick={() => toggleSort("return")}
                  className="p-3 font-medium text-right cursor-pointer hover:text-quant-textPrimary"
                >
                  <span className="flex items-center justify-end gap-1">
                    ML 5D PRED <ArrowUpDown className="w-3 h-3" />
                  </span>
                </th>
                <th className="p-3 font-medium text-right">CONF</th>
                <th className="p-3 font-medium text-center">MOMENTUM</th>
                <th
                  onClick={() => toggleSort("volatility")}
                  className="p-3 font-medium text-center cursor-pointer hover:text-quant-textPrimary"
                >
                  <span className="flex items-center justify-center gap-1">
                    VOLATILITY <ArrowUpDown className="w-3 h-3" />
                  </span>
                </th>
                <th className="p-3 font-medium text-right">REL STRENGTH</th>
                <th className="p-3 font-medium">SECTOR</th>
                <th className="p-3 font-medium text-center">RISK STATUS</th>
              </tr>
            </thead>

            <tbody className="divide-y divide-quant-border">
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={11} className="p-8 text-center text-quant-textMuted">
                    No equities matched current filter criteria.
                  </td>
                </tr>
              ) : (
                filtered.map((item) => {
                  const hasPred = item.predicted_return !== null && item.predicted_return !== undefined;
                  const isBull = hasPred && item.predicted_return! >= 0.01;
                  const isBear = hasPred && item.predicted_return! <= -0.01;
                  return (
                    <tr
                      key={item.symbol}
                      onClick={() => onSelectStock(item.symbol)}
                      className="hover:bg-quant-surface/60 cursor-pointer transition-colors group"
                    >
                      <td className="p-3 font-bold text-quant-cyan">
                        #{item.rank}
                      </td>

                      <td className="p-3">
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-quant-textPrimary group-hover:text-quant-cyan">
                            {item.symbol}
                          </span>
                          <span className="text-[10px] text-quant-textMuted font-normal truncate max-w-[130px] hidden md:inline">
                            {item.company_name}
                          </span>
                        </div>
                      </td>

                      <td className="p-3 text-right font-medium text-quant-textSecondary">
                        {item.price > 0 ? `₹${item.price.toFixed(2)}` : "Not available"}
                      </td>

                      <td className="p-3 text-right">
                        {item.quant_score !== null && item.quant_score !== undefined ? (
                          <span className="font-bold text-quant-cyan bg-quant-cyanMuted px-2 py-0.5 rounded border border-quant-cyan/30">
                            {item.quant_score.toFixed(1)}
                          </span>
                        ) : (
                          <span className="text-quant-textMuted">N/A</span>
                        )}
                      </td>

                      <td
                        className={`p-3 text-right font-bold ${
                          !hasPred ? "text-quant-textMuted" : isBull ? "text-quant-bull" : isBear ? "text-quant-bear" : "text-quant-textSecondary"
                        }`}
                      >
                        {hasPred
                          ? item.predicted_return! >= 0
                            ? `+${(item.predicted_return! * 100).toFixed(2)}%`
                            : `${(item.predicted_return! * 100).toFixed(2)}%`
                          : "N/A"}
                      </td>

                      <td className="p-3 text-right text-quant-textMuted">
                        {item.confidence !== null && item.confidence !== undefined
                          ? `${(item.confidence * 100).toFixed(0)}%`
                          : "N/A"}
                      </td>

                      <td className="p-3 text-center">
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
                            item.momentum === "Strong"
                              ? "bg-quant-bullMuted text-quant-bull border border-quant-bull/30"
                              : item.momentum === "Weak"
                              ? "bg-quant-bearMuted text-quant-bear border border-quant-bear/30"
                              : "bg-quant-surface text-quant-textMuted border border-quant-border"
                          }`}
                        >
                          {item.momentum}
                        </span>
                      </td>

                      <td className="p-3 text-center">
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
                            item.volatility === "Low"
                              ? "text-quant-bull"
                              : item.volatility === "High"
                              ? "text-quant-bear"
                              : "text-quant-warn"
                          }`}
                        >
                          {item.volatility} ({item.volatility_20d.toFixed(1)}%)
                        </span>
                      </td>

                      <td className="p-3 text-right text-quant-textSecondary">
                        {item.relative_strength >= 0 ? `+${item.relative_strength.toFixed(1)}%` : `${item.relative_strength.toFixed(1)}%`}
                      </td>

                      <td className="p-3 text-quant-textSecondary">
                        {item.sector}
                      </td>

                      <td className="p-3 text-center">
                        <StatusBadge status={item.risk_status} size="sm" />
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        <div className="p-3 bg-quant-surface border-t border-quant-border flex items-center justify-between text-[11px] font-mono text-quant-textMuted">
          <span>Displaying {filtered.length} of {items.length} ranked equities</span>
          <span>Click any row to open Stock Intelligence</span>
        </div>
      </div>
    </div>
  );
};
