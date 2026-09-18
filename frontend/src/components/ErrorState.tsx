import React from "react";
import { AlertCircle, RefreshCw, Database } from "lucide-react";

interface ErrorStateProps {
  message?: string;
  onRetry?: () => void;
  title?: string;
}

export const ErrorState: React.FC<ErrorStateProps> = ({
  message = "An error occurred while fetching telemetry from the backend API.",
  onRetry,
  title = "DATA FETCH FAILED",
}) => {
  return (
    <div className="quant-card p-8 text-center flex flex-col items-center justify-center my-6">
      <div className="w-12 h-12 rounded-full bg-quant-bearMuted flex items-center justify-center text-quant-bear mb-3 border border-quant-bear/30">
        <AlertCircle className="w-6 h-6" />
      </div>
      <h3 className="font-mono font-bold text-sm text-quant-textPrimary tracking-wide mb-1">
        {title}
      </h3>
      <p className="text-xs text-quant-textSecondary max-w-md mb-4 leading-relaxed">
        {message}
      </p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="flex items-center gap-2 px-4 py-1.5 bg-quant-card hover:bg-quant-elevated text-xs font-mono font-medium text-quant-cyan border border-quant-cyan/40 hover:border-quant-cyan rounded transition-colors"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          Retry Request
        </button>
      )}
    </div>
  );
};

interface EmptyStateProps {
  title?: string;
  message?: string;
  icon?: React.ReactNode;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  title = "NO DATA AVAILABLE",
  message = "No records or active positions returned by backend storage.",
  icon,
}) => {
  return (
    <div className="quant-card p-8 text-center flex flex-col items-center justify-center my-6">
      <div className="w-12 h-12 rounded-full bg-quant-surface flex items-center justify-center text-quant-textMuted mb-3 border border-quant-border">
        {icon || <Database className="w-6 h-6" />}
      </div>
      <h3 className="font-mono font-bold text-sm text-quant-textSecondary tracking-wide mb-1">
        {title}
      </h3>
      <p className="text-xs text-quant-textMuted max-w-sm leading-relaxed">
        {message}
      </p>
    </div>
  );
};

export const LoadingState: React.FC<{ message?: string }> = ({
  message = "Synchronizing with APEX-QUANT backend telemetry...",
}) => {
  return (
    <div className="quant-card p-12 text-center flex flex-col items-center justify-center my-6">
      <div className="relative mb-3">
        <div className="w-8 h-8 rounded-full border-2 border-quant-cyan/20 border-t-quant-cyan animate-spin" />
      </div>
      <p className="text-xs font-mono text-quant-textSecondary tracking-wide">
        {message}
      </p>
    </div>
  );
};
