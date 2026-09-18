import React from "react";
import { ExternalLink, AlertTriangle, ShieldAlert, Cpu, Terminal } from "lucide-react";

export const LegacyBinance: React.FC = () => {
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-quant-border pb-3">
        <div>
          <h2 className="font-mono text-lg font-bold text-quant-textPrimary flex items-center gap-2">
            LEGACY BINANCE TESTNET BOT
            <span className="text-xs font-normal text-quant-warn bg-quant-warnMuted px-2 py-0.5 rounded border border-quant-warn/30">
              ISOLATED CRYPTO TERMINAL
            </span>
          </h2>
          <p className="text-xs text-quant-textSecondary">
            Isolated high-frequency tick momentum trading bot operating on Binance Spot Testnet (BTC/USDT).
          </p>
        </div>

        <a
          href="/dashboard-compact"
          target="_blank"
          rel="noreferrer"
          className="flex items-center gap-1.5 px-3 py-1.5 bg-quant-card hover:bg-quant-surface border border-quant-border rounded text-xs font-mono text-quant-cyan hover:border-quant-cyan transition-colors"
        >
          <ExternalLink className="w-3.5 h-3.5" />
          Open Legacy UI in New Tab
        </a>
      </div>

      {/* Strict Isolation Notice */}
      <div className="bg-quant-card border-l-4 border-quant-warn p-4 rounded-r-lg">
        <div className="flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-quant-warn shrink-0 mt-0.5" />
          <div className="text-xs leading-relaxed">
            <h4 className="font-mono font-bold text-quant-warn uppercase mb-1">
              LOGICAL ISOLATION ENFORCED — ZERO METRIC CONTAMINATION
            </h4>
            <p className="text-quant-textSecondary">
              This legacy Binance bot runs independently via <code className="text-quant-cyan">cpp_trading_bot</code> and <code className="text-quant-cyan">bot_state.json</code>.
              Crypto Testnet balances, P&L, and orders are <strong>strictly quarantined</strong> and never mixed with Indian equity portfolio NAV or paper trading accounting.
            </p>
          </div>
        </div>
      </div>

      {/* Embedded Legacy Dashboard Iframe */}
      <div className="quant-card overflow-hidden rounded-xl border border-quant-border">
        <div className="p-3 bg-quant-surface border-b border-quant-border flex items-center justify-between font-mono text-xs text-quant-textSecondary">
          <div className="flex items-center gap-2">
            <Terminal className="w-4 h-4 text-quant-cyan" />
            <span className="font-bold text-quant-textPrimary">SANDBOX FRAME: /dashboard-compact</span>
          </div>
          <span className="text-[11px] text-quant-textMuted">Binance Testnet Tick Momentum Engine</span>
        </div>

        <div className="w-full h-[650px] bg-black">
          <iframe
            src="/dashboard-compact"
            title="Legacy Binance Bot Dashboard"
            className="w-full h-full border-0"
          />
        </div>
      </div>
    </div>
  );
};
