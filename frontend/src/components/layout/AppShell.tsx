import React, { useState } from "react";
import { Sidebar } from "./Sidebar";
import { Navbar } from "./Navbar";
import { CommandPalette } from "../ui/CommandPalette";
import { TooltipProvider } from "../ui/Tooltip";

export function AppShell({ children }: { children: React.ReactNode }) {
  const [cmdOpen, setCmdOpen] = useState(false);

  return (
    <TooltipProvider>
      <div className="flex h-screen w-full bg-quant-bg text-quant-textPrimary overflow-hidden font-sans">
        <Sidebar />
        <div className="flex-1 flex flex-col h-full overflow-hidden">
          <Navbar onSearchClick={() => setCmdOpen(true)} />
          <main className="flex-1 overflow-y-auto p-6">
            <div className="max-w-7xl mx-auto w-full">
              {children}
            </div>
          </main>
        </div>
        <CommandPalette open={cmdOpen} setOpen={setCmdOpen} />
      </div>
    </TooltipProvider>
  );
}
