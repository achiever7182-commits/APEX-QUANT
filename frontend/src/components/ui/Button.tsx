import * as React from "react"
import { cn } from "../../utils/cn"

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "default" | "outline" | "ghost" | "destructive";
  size?: "default" | "sm" | "lg" | "icon";
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "default", size = "default", ...props }, ref) => {
    const baseStyles = "inline-flex items-center justify-center whitespace-nowrap rounded-sm text-sm font-medium ring-offset-quant-bg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-quant-border focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50"
    
    const variants = {
      default: "bg-zinc-100 text-zinc-900 hover:bg-zinc-200",
      outline: "border border-quant-border bg-quant-bg hover:bg-quant-surface text-quant-textPrimary",
      ghost: "hover:bg-quant-surface text-quant-textPrimary",
      destructive: "bg-red-900 text-zinc-50 hover:bg-red-900/90",
    }
    
    const sizes = {
      default: "h-9 px-4 py-2",
      sm: "h-8 rounded-sm px-3 text-xs",
      lg: "h-10 rounded-sm px-8",
      icon: "h-9 w-9",
    }

    return (
      <button
        ref={ref}
        className={cn(baseStyles, variants[variant], sizes[size], className)}
        {...props}
      />
    )
  }
)
Button.displayName = "Button"
