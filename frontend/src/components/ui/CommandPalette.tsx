import React, { useEffect } from "react";
import { Command } from "cmdk";
import { Dialog, DialogContent } from "./Dialog";
import { useNavigate } from "react-router-dom";
import { Search } from "lucide-react";

export function CommandPalette({ open, setOpen }: { open: boolean, setOpen: (open: boolean) => void }) {
  const navigate = useNavigate();

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen(true);
      }
    };

    document.addEventListener("keydown", down);
    return () => document.removeEventListener("keydown", down);
  }, [setOpen]);

  const runCommand = (command: () => void) => {
    setOpen(false);
    command();
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="overflow-hidden p-0 bg-quant-bg border border-zinc-800 shadow-2xl rounded-sm">
        <Command className="w-full flex flex-col">
          <div className="flex items-center border-b border-zinc-800 px-3">
            <Search className="mr-2 h-4 w-4 shrink-0 text-quant-textSecondary" />
            <Command.Input
              className="flex h-12 w-full rounded-sm bg-transparent py-3 text-sm outline-none placeholder:text-quant-textMuted text-zinc-100 disabled:cursor-not-allowed disabled:opacity-50"
              placeholder="Type a command or search..."
            />
          </div>
          <Command.List className="max-h-[300px] overflow-y-auto overflow-x-hidden p-2 text-sm text-zinc-100">
            <Command.Empty className="py-6 text-center text-sm text-quant-textSecondary">
              No results found.
            </Command.Empty>
            
            <Command.Group heading="Navigation" className="text-xs text-quant-textMuted font-semibold px-2 py-1.5 [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:text-quant-textMuted">
              <Command.Item
                onSelect={() => runCommand(() => navigate("/dashboard"))}
                className="relative flex cursor-default select-none items-center rounded-sm px-2 py-1.5 text-sm outline-none data-[selected=true]:bg-zinc-800 data-[selected=true]:text-zinc-100"
              >
                Dashboard
              </Command.Item>
              <Command.Item
                onSelect={() => runCommand(() => navigate("/market"))}
                className="relative flex cursor-default select-none items-center rounded-sm px-2 py-1.5 text-sm outline-none data-[selected=true]:bg-zinc-800 data-[selected=true]:text-zinc-100"
              >
                Market Overview
              </Command.Item>
              <Command.Item
                onSelect={() => runCommand(() => navigate("/portfolio"))}
                className="relative flex cursor-default select-none items-center rounded-sm px-2 py-1.5 text-sm outline-none data-[selected=true]:bg-zinc-800 data-[selected=true]:text-zinc-100"
              >
                Portfolio
              </Command.Item>
              <Command.Item
                onSelect={() => runCommand(() => navigate("/system"))}
                className="relative flex cursor-default select-none items-center rounded-sm px-2 py-1.5 text-sm outline-none data-[selected=true]:bg-zinc-800 data-[selected=true]:text-zinc-100"
              >
                System Health
              </Command.Item>
            </Command.Group>

            <Command.Group heading="Research" className="text-xs text-quant-textMuted font-semibold px-2 py-1.5 mt-2 [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:text-quant-textMuted">
              <Command.Item
                onSelect={() => runCommand(() => navigate("/signals"))}
                className="relative flex cursor-default select-none items-center rounded-sm px-2 py-1.5 text-sm outline-none data-[selected=true]:bg-zinc-800 data-[selected=true]:text-zinc-100"
              >
                Quantitative Signals
              </Command.Item>
              <Command.Item
                onSelect={() => runCommand(() => navigate("/backtests"))}
                className="relative flex cursor-default select-none items-center rounded-sm px-2 py-1.5 text-sm outline-none data-[selected=true]:bg-zinc-800 data-[selected=true]:text-zinc-100"
              >
                Run Backtest
              </Command.Item>
              <Command.Item
                onSelect={() => runCommand(() => navigate("/models"))}
                className="relative flex cursor-default select-none items-center rounded-sm px-2 py-1.5 text-sm outline-none data-[selected=true]:bg-zinc-800 data-[selected=true]:text-zinc-100"
              >
                Model Registry
              </Command.Item>
            </Command.Group>

            <Command.Separator className="my-1 h-px bg-zinc-800" />
            
            <Command.Group heading="Actions" className="text-xs text-quant-textMuted font-semibold px-2 py-1.5 [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:text-quant-textMuted">
              <Command.Item
                className="relative flex cursor-default select-none items-center rounded-sm px-2 py-1.5 text-sm outline-none opacity-50"
              >
                Refresh Data (Disabled in PAPER)
              </Command.Item>
            </Command.Group>
          </Command.List>
        </Command>
      </DialogContent>
    </Dialog>
  );
}
