import * as React from "react"
import { cn } from "../../utils/cn"

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "default" | "secondary" | "outline" | "bull" | "bear" | "warn";
}

export function Badge({ className, variant = "default", ...props }: BadgeProps) {
  const baseStyles = "inline-flex items-center rounded-sm border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-quant-border focus:ring-offset-2"
  
  const variants = {
    default: "border-transparent bg-zinc-100 text-zinc-900 hover:bg-zinc-200",
    secondary: "border-transparent bg-quant-surface text-quant-textSecondary hover:bg-quant-surface/80",
    outline: "text-quant-textPrimary border-quant-border",
    bull: "border-transparent bg-zinc-300 text-zinc-900",
    bear: "border-transparent bg-zinc-700 text-zinc-100",
    warn: "border-transparent bg-zinc-500 text-zinc-100",
  }

  return (
    <div className={cn(baseStyles, variants[variant], className)} {...props} />
  )
}
