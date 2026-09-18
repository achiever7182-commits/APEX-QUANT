import React, { useState } from "react";
import { AlertTriangle, Power, X, ShieldCheck } from "lucide-react";
import { api } from "../api/client";

interface KillSwitchModalProps {
  isOpen: boolean;
  isActive: boolean;
  onClose: () => void;
  onToggleSuccess: (newStatus: { active: boolean; reason?: string }) => void;
}

export const KillSwitchModal: React.FC<KillSwitchModalProps> = ({
  isOpen,
  isActive,
  onClose,
  onToggleSuccess,
}) => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleToggle = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.toggleKillSwitch();
      onToggleSuccess(res);
      onClose();
    } catch (err: any) {
      setError(err?.message || "Failed to toggle kill switch.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
      <div className="bg-quant-surface border border-quant-borderBright w-full max-w-md rounded-xl p-6 shadow-2xl relative">
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-quant-textMuted hover:text-quant-textPrimary"
        >
          <X className="w-5 h-5" />
        </button>

        <div className="flex items-center gap-3 text-quant-warn mb-4">
          <div className={`p-3 rounded-lg ${isActive ? "bg-quant-bullMuted text-quant-bull" : "bg-quant-bearMuted text-quant-bear"}`}>
            <Power className="w-6 h-6" />
          </div>
          <div>
            <h3 className="text-lg font-bold text-quant-textPrimary">
              {isActive ? "Disarm Kill Switch?" : "Arm Persistent Kill Switch?"}
            </h3>
            <p className="text-xs text-quant-textSecondary">
              Current Status: <span className="font-mono font-semibold">{isActive ? "ENGAGED (ORDERS BLOCKED)" : "DISARMED (NORMAL)"}</span>
            </p>
          </div>
        </div>

        <div className="bg-quant-card border border-quant-border rounded-lg p-3 text-xs leading-relaxed text-quant-textSecondary mb-5 space-y-2">
          <p className="flex items-start gap-1.5 text-quant-textPrimary">
            <AlertTriangle className="w-4 h-4 text-quant-warn shrink-0 mt-0.5" />
            <span>
              {isActive
                ? "Disarming will allow the paper execution engine to resume generating and submitting new virtual paper orders."
                : "Engaging the kill switch immediately blocks ALL new paper order submissions across the system."}
            </span>
          </p>
          <p className="text-[11px] text-quant-textMuted">
            Note: This action strictly governs paper trading order dispatch. It does <strong>NOT</strong> silently liquidate existing holdings. State is persistently preserved on disk in <code className="font-mono text-quant-cyan">kill_switch.json</code>.
          </p>
        </div>

        {error && (
          <div className="mb-4 p-2 bg-quant-bearMuted border border-quant-bear/40 text-quant-bear text-xs rounded">
            {error}
          </div>
        )}

        <div className="flex items-center justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 text-xs font-medium text-quant-textSecondary hover:text-quant-textPrimary border border-quant-border hover:border-quant-borderBright rounded-lg transition-colors"
          >
            Cancel
          </button>

          <button
            onClick={handleToggle}
            disabled={loading}
            className={`px-5 py-2 text-xs font-bold rounded-lg transition-all flex items-center gap-2 ${
              isActive
                ? "bg-quant-bull hover:bg-quant-bull/90 text-quant-bg"
                : "bg-quant-bear hover:bg-quant-bear/90 text-white"
            } disabled:opacity-50`}
          >
            {loading ? (
              <span>Updating...</span>
            ) : isActive ? (
              <>
                <ShieldCheck className="w-4 h-4" />
                Disarm & Resume Paper Orders
              </>
            ) : (
              <>
                <Power className="w-4 h-4" />
                Engage Kill Switch (Halt Orders)
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
};
