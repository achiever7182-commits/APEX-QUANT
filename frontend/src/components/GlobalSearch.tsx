import React, { useState, useEffect, useRef } from "react";
import { Search, X, ChevronRight, TrendingUp } from "lucide-react";
import type { UniverseConstituent } from "../types";
import { api } from "../api/client";

interface GlobalSearchProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectSymbol: (symbol: string) => void;
}

export const GlobalSearch: React.FC<GlobalSearchProps> = ({
  isOpen,
  onClose,
  onSelectSymbol,
}) => {
  const [query, setQuery] = useState("");
  const [universe, setUniverse] = useState<UniverseConstituent[]>([]);
  const [loading, setLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isOpen) {
      setQuery("");
      inputRef.current?.focus();
      if (universe.length === 0) {
        setLoading(true);
        api.getUniverse()
          .then((data) => setUniverse(data.universe || []))
          .catch(() => {})
          .finally(() => setLoading(false));
      }
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const filtered = universe.filter((s) => {
    const q = query.toLowerCase().trim();
    if (!q) return true;
    return (
      s.symbol.toLowerCase().includes(q) ||
      s.company_name.toLowerCase().includes(q) ||
      s.sector.toLowerCase().includes(q)
    );
  }).slice(0, 10);

  const handleSelect = (sym: string) => {
    onSelectSymbol(sym);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-20 bg-black/80 backdrop-blur-sm p-4">
      <div className="bg-quant-surface border border-quant-borderBright w-full max-w-xl rounded-xl shadow-2xl overflow-hidden">
        <div className="p-3 border-b border-quant-border flex items-center gap-3">
          <Search className="w-5 h-5 text-quant-cyan shrink-0" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search 50 active Indian equities by Symbol, Company, or Sector (e.g. RELIANCE, TCS, Energy)..."
            className="w-full bg-transparent border-none outline-none text-sm text-quant-textPrimary placeholder:text-quant-textMuted font-mono"
          />
          <button onClick={onClose} className="text-quant-textMuted hover:text-quant-textPrimary">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="max-h-80 overflow-y-auto divide-y divide-quant-border">
          {loading ? (
            <div className="p-6 text-center text-xs text-quant-textMuted font-mono">
              Loading universe catalog...
            </div>
          ) : filtered.length === 0 ? (
            <div className="p-6 text-center text-xs text-quant-textMuted font-mono">
              No matching equities found in tracked universe.
            </div>
          ) : (
            filtered.map((stock) => (
              <div
                key={stock.symbol}
                onClick={() => handleSelect(stock.symbol)}
                className="p-3 flex items-center justify-between hover:bg-quant-card cursor-pointer transition-colors group"
              >
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded bg-quant-card flex items-center justify-center font-mono font-bold text-xs text-quant-cyan border border-quant-border group-hover:border-quant-cyan">
                    {stock.symbol.slice(0, 2)}
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-mono font-bold text-sm text-quant-textPrimary group-hover:text-quant-cyan">
                        {stock.symbol}
                      </span>
                      <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-quant-surface border border-quant-border text-quant-textMuted">
                        {stock.exchange}
                      </span>
                    </div>
                    <div className="text-xs text-quant-textSecondary truncate max-w-sm">
                      {stock.company_name}
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-4 text-right">
                  <div className="hidden sm:block">
                    <div className="text-xs font-medium text-quant-textSecondary">{stock.sector}</div>
                    <div className="text-[10px] text-quant-textMuted">{stock.industry}</div>
                  </div>
                  <ChevronRight className="w-4 h-4 text-quant-textMuted group-hover:text-quant-cyan group-hover:translate-x-0.5 transition-all" />
                </div>
              </div>
            ))
          )}
        </div>

        <div className="px-3 py-2 bg-quant-card border-t border-quant-border flex items-center justify-between text-[11px] text-quant-textMuted font-mono">
          <span>Esc to exit</span>
          <span>NIFTY 50 Universe Tracked ({universe.length} Constituents)</span>
        </div>
      </div>
    </div>
  );
};
