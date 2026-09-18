import React, { useEffect, useState } from "react";
import { Search, ArrowUpDown, Clock, Zap, Info, ArrowUpRight, ArrowDownRight } from "lucide-react";
import { api } from "../api/client";
import { LoadingState, ErrorState } from "../components/ErrorState";
import { StatusBadge } from "../components/StatusBadge";
import type { RealtimeFeedHealth, RealtimeQuote, UniverseConstituent } from "../types";

interface MarketProps {
  onSelectStock: (symbol: string) => void;
}

export const Market: React.FC<MarketProps> = ({ onSelectStock }) => {
  const [universe, setUniverse] = useState<UniverseConstituent[]>([]);
  const [quotes, setQuotes] = useState<Record<string, RealtimeQuote>>({});
  const [feedHealth, setFeedHealth] = useState<RealtimeFeedHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [selectedSector, setSelectedSector] = useState<string>("ALL");
  const [sortField, setSortField] = useState<"symbol" | "price" | "volume" | "age">("symbol");
  const [sortAsc, setSortAsc] = useState(true);

  const fetchData = async () => {
    try {
      setError(null);
      const [uRes, qRes, hRes] = await Promise.all([
        api.getUniverse(),
        api.getQuotes(),
        api.getRealtimeHealth().catch(() => null),
      ]);
      setUniverse(uRes.universe || []);
      setQuotes(qRes.quotes || {});
      if (hRes) setFeedHealth(hRes);
    } catch (err: any) {
      setError(err?.message || "Failed to load market data feed.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5000); // 5s refresh
    return () => clearInterval(interval);
  }, []);

  if (loading) return <LoadingState message="Fetching market quotes & universe constituents..." />;
  if (error && universe.length === 0) return <ErrorState message={error} onRetry={fetchData} />;

  const sectors = ["ALL", ...Array.from(new Set(universe.map((u) => u.sector || "General"))).sort()];

  // Combine universe items with quotes
  const combined = universe.map((stock) => {
    const q = quotes[stock.symbol];
    return {
      symbol: stock.symbol,
      company_name: stock.company_name,
      sector: stock.sector,
      industry: stock.industry,
      isin: stock.isin,
      last_price: q?.last_price ?? 0,
      bid: q?.bid ?? 0,
      ask: q?.ask ?? 0,
      spread: q && q.ask && q.bid ? Math.max(0, q.ask - q.bid) : 0,
      volume: q?.volume ?? 0,
      age_seconds: q?.age_seconds ?? null,
      timestamp: q?.timestamp ?? null,
      data_source: q?.data_source ?? "PARQUET_HISTORICAL",
    };
  });

  const filtered = combined.filter((item) => {
    const matchesSearch =
      item.symbol.toLowerCase().includes(search.toLowerCase().trim()) ||
      item.company_name.toLowerCase().includes(search.toLowerCase().trim());
    const matchesSector = selectedSector === "ALL" || item.sector === selectedSector;
    return matchesSearch && matchesSector;
  });

  filtered.sort((a, b) => {
    let comparison = 0;
    if (sortField === "symbol") comparison = a.symbol.localeCompare(b.symbol);
    if (sortField === "price") comparison = a.last_price - b.last_price;
    if (sortField === "volume") comparison = a.volume - b.volume;
    if (sortField === "age") comparison = (a.age_seconds ?? 9999) - (b.age_seconds ?? 9999);
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
      {/* Header & Source Notice */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-quant-border pb-3">
        <div>
          <h2 className="font-mono text-lg font-bold text-quant-textPrimary flex items-center gap-2">
            MARKET OVERVIEW
            <span className="text-xs font-normal text-quant-cyan bg-quant-cyanMuted px-2 py-0.5 rounded border border-quant-cyan/30">
              CURATED 52-STOCK CATALOG
            </span>
          </h2>
          <p className="text-xs text-quant-textSecondary">
            Live quote telemetry, order book bid/ask spreads, and data freshness across the curated 52 Indian equity catalog (with 5-stock empirical research validation dataset).
          </p>
        </div>

        {/* Realtime Provider Honesty Banner */}
        <div className="flex items-center gap-2 bg-quant-card border border-quant-border px-3 py-1.5 rounded-lg text-xs font-mono">
          <Info className="w-3.5 h-3.5 text-quant-cyan shrink-0" />
          <span className="text-quant-textMuted">Provider:</span>
          <span className="text-quant-warn font-semibold">MOCK REALTIME PROVIDER</span>
          <span className="text-quant-borderBright">|</span>
          <span className="text-quant-textMuted">Status:</span>
          <StatusBadge status={feedHealth?.market_session || "REGULAR"} size="sm" />
        </div>
      </div>

      {/* Filter & Search Bar */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 bg-quant-card border border-quant-border p-3 rounded-lg">
        <div className="relative flex-1 max-w-md">
          <Search className="w-4 h-4 text-quant-textMuted absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by symbol or company..."
            className="w-full pl-9 pr-3 py-1.5 bg-quant-surface border border-quant-border rounded text-xs font-mono text-quant-textPrimary placeholder:text-quant-textMuted focus:outline-none focus:border-quant-cyan"
          />
        </div>

        <div className="flex items-center gap-2 overflow-x-auto scrollbar-none">
          <span className="text-xs font-mono text-quant-textMuted whitespace-nowrap">SECTOR:</span>
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
      </div>

      {/* Market Table */}
      <div className="quant-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs font-mono">
            <thead className="bg-quant-surface border-b border-quant-border text-quant-textMuted text-[11px]">
              <tr>
                <th
                  onClick={() => toggleSort("symbol")}
                  className="p-3 font-medium cursor-pointer hover:text-quant-textPrimary"
                >
                  <span className="flex items-center gap-1">
                    SYMBOL / COMPANY <ArrowUpDown className="w-3 h-3" />
                  </span>
                </th>
                <th className="p-3 font-medium">SECTOR</th>
                <th
                  onClick={() => toggleSort("price")}
                  className="p-3 font-medium text-right cursor-pointer hover:text-quant-textPrimary"
                >
                  <span className="flex items-center justify-end gap-1">
                    LAST PRICE <ArrowUpDown className="w-3 h-3" />
                  </span>
                </th>
                <th className="p-3 font-medium text-right">BID / ASK</th>
                <th className="p-3 font-medium text-right">SPREAD</th>
                <th
                  onClick={() => toggleSort("volume")}
                  className="p-3 font-medium text-right cursor-pointer hover:text-quant-textPrimary"
                >
                  <span className="flex items-center justify-end gap-1">
                    VOLUME <ArrowUpDown className="w-3 h-3" />
                  </span>
                </th>
                <th
                  onClick={() => toggleSort("age")}
                  className="p-3 font-medium text-right cursor-pointer hover:text-quant-textPrimary"
                >
                  <span className="flex items-center justify-end gap-1">
                    AGE / SOURCE <ArrowUpDown className="w-3 h-3" />
                  </span>
                </th>
              </tr>
            </thead>

            <tbody className="divide-y divide-quant-border">
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={7} className="p-8 text-center text-quant-textMuted">
                    No matching stocks found in active market universe.
                  </td>
                </tr>
              ) : (
                filtered.map((stock) => {
                  const isStale = stock.age_seconds !== null && stock.age_seconds > 300;
                  return (
                    <tr
                      key={stock.symbol}
                      onClick={() => onSelectStock(stock.symbol)}
                      className="hover:bg-quant-surface/60 cursor-pointer transition-colors group"
                    >
                      <td className="p-3">
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-quant-textPrimary group-hover:text-quant-cyan">
                            {stock.symbol}
                          </span>
                          <span className="text-[10px] text-quant-textMuted font-normal truncate max-w-[200px]">
                            {stock.company_name}
                          </span>
                        </div>
                      </td>

                      <td className="p-3 text-quant-textSecondary">
                        {stock.sector}
                      </td>

                      <td className="p-3 text-right font-bold text-quant-textPrimary">
                        {stock.last_price > 0 ? `₹${stock.last_price.toFixed(2)}` : "N/A"}
                      </td>

                      <td className="p-3 text-right text-quant-textMuted">
                        {stock.bid > 0 ? (
                          <span>
                            <span className="text-quant-bull">₹{stock.bid.toFixed(2)}</span>
                            {" / "}
                            <span className="text-quant-bear">₹{stock.ask.toFixed(2)}</span>
                          </span>
                        ) : (
                          "N/A"
                        )}
                      </td>

                      <td className="p-3 text-right text-quant-textMuted">
                        {stock.spread > 0 ? `₹${stock.spread.toFixed(2)}` : "—"}
                      </td>

                      <td className="p-3 text-right font-medium text-quant-textSecondary">
                        {stock.volume > 0 ? stock.volume.toLocaleString("en-IN") : "—"}
                      </td>

                      <td className="p-3 text-right">
                        <div className="flex flex-col items-end">
                          <span
                            className={`font-medium ${
                              isStale
                                ? "text-quant-bear"
                                : stock.age_seconds !== null
                                ? "text-quant-bull"
                                : "text-quant-textMuted"
                            }`}
                          >
                            {stock.age_seconds !== null ? `${stock.age_seconds.toFixed(0)}s ago` : "HISTORICAL"}
                          </span>
                          <span className="text-[10px] text-quant-textMuted uppercase">
                            {stock.data_source}
                          </span>
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        <div className="p-3 bg-quant-surface border-t border-quant-border flex items-center justify-between text-[11px] font-mono text-quant-textMuted">
          <span>Displaying {filtered.length} of {universe.length} equities</span>
          <span>Click any symbol to launch Stock Intelligence workstation</span>
        </div>
      </div>
    </div>
  );
};
