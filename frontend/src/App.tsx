import React from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { AppShell } from "./components/layout/AppShell";

// Pages
import Dashboard from "./pages/dashboard";
import Market from "./pages/market";
import Signals from "./pages/signals";
import Portfolio from "./pages/portfolio";
import Positions from "./pages/positions";
import Backtests from "./pages/backtests";
import Models from "./pages/models";
import DataPipeline from "./pages/data";
import System from "./pages/system";
import Settings from "./pages/settings";

export default function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/market" element={<Market />} />
        <Route path="/signals" element={<Signals />} />
        <Route path="/portfolio" element={<Portfolio />} />
        <Route path="/positions" element={<Positions />} />
        <Route path="/backtests" element={<Backtests />} />
        <Route path="/models" element={<Models />} />
        <Route path="/data" element={<DataPipeline />} />
        <Route path="/system" element={<System />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </AppShell>
  );
}
