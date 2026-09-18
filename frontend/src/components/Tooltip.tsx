import React, { useState } from "react";
import { HelpCircle } from "lucide-react";

const GLOSSARY: Record<string, string> = {
  "Sharpe Ratio": "Annualized risk-adjusted excess return per unit of volatility. Assumes 6.5% risk-free rate. Historical simulation metric only.",
  "Sortino Ratio": "Risk-adjusted return focusing exclusively on downside volatility rather than total variance. Historical simulation metric only.",
  "CAGR": "Compound Annual Growth Rate of simulated portfolio equity across trading sessions under realistic transaction costs.",
  "Information Coefficient (IC)": "Spearman rank correlation between cross-sectional model predictions and realized 5-day forward returns.",
  "IC IR": "Information Ratio of the IC (mean IC / standard deviation of IC) measuring signal consistency over time.",
  "Quant Score": "Cross-sectional ranking metric (0–100) combining ML predicted returns, 14-day RSI momentum, and 20-day annualized volatility.",
  "Max Drawdown": "Maximum peak-to-trough decline of simulated portfolio equity. Enforced by a strict 10% circuit breaker.",
  "Turnover": "Ratio of traded value to total portfolio equity. Reflects transaction friction and rebalancing volume.",
  "Gross Exposure": "Total position market value divided by total portfolio equity. Capped at 100% (zero borrowing or leverage).",
  "Sector Exposure": "Total market value of positions within a single GICS sector. Capped at 55% to enforce macro diversification.",
  "Single Stock Concentration": "Weight of the largest individual stock position. Capped at 35% to prevent idiosyncratic blowups.",
  "Liquidity Limit": "Order sizing limit ensuring trade volume does not exceed 5% of 20-day historical median daily volume.",
};

interface TooltipProps {
  term: string;
  customText?: string;
  children?: React.ReactNode;
}

export const Tooltip: React.FC<TooltipProps> = ({ term, customText, children }) => {
  const [visible, setVisible] = useState(false);
  const description = customText || GLOSSARY[term] || term;

  return (
    <span
      className="relative inline-flex items-center gap-1 cursor-help group"
      onMouseEnter={() => setVisible(true)}
      onMouseLeave={() => setVisible(false)}
    >
      {children ? children : <span>{term}</span>}
      <HelpCircle className="w-3 h-3 text-quant-textMuted group-hover:text-quant-cyan transition-colors" />

      {visible && (
        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 w-64 p-2.5 bg-quant-surface border border-quant-borderBright rounded shadow-2xl text-[11px] leading-relaxed text-quant-textPrimary z-50 pointer-events-none">
          <div className="font-semibold text-quant-cyan mb-1">{term}</div>
          <div className="text-quant-textSecondary">{description}</div>
        </div>
      )}
    </span>
  );
};
