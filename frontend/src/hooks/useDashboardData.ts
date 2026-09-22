import { useState, useEffect } from "react";
import { api } from "../api/client";
import { AccountSummary, RealtimeFeedHealth, Position } from "../types";

export function useDashboardData() {
  const [summary, setSummary] = useState<AccountSummary | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [health, setHealth] = useState<RealtimeFeedHealth | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;

    async function fetchData() {
      try {
        const [sumRes, posRes, healthRes] = await Promise.all([
          api.getAccountSummary().catch(() => null),
          api.getPositions().catch(() => []),
          api.getRealtimeHealth().catch(() => null)
        ]);

        if (mounted) {
          setSummary(sumRes);
          setPositions(posRes);
          setHealth(healthRes);
          setLoading(false);
        }
      } catch (err) {
        if (mounted) setLoading(false);
      }
    }

    fetchData();
    const interval = setInterval(fetchData, 5000); // Polling every 5s

    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  return { summary, positions, health, loading };
}
