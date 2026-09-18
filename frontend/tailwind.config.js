/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        quant: {
          bg: "#080c14",
          surface: "#0f1626",
          card: "#131c31",
          elevated: "#18243e",
          border: "#1e2c48",
          borderBright: "#2c3e66",
          cyan: "#00d4ff",
          cyanMuted: "rgba(0, 212, 255, 0.15)",
          blue: "#3b82f6",
          bull: "#10b981",
          bullMuted: "rgba(16, 185, 129, 0.15)",
          bear: "#f43f5e",
          bearMuted: "rgba(244, 63, 94, 0.15)",
          warn: "#f59e0b",
          warnMuted: "rgba(245, 158, 11, 0.15)",
          textPrimary: "#f1f5f9",
          textSecondary: "#94a3b8",
          textMuted: "#64748b",
        },
      },
      fontFamily: {
        mono: ["'JetBrains Mono'", "'SF Mono'", "'Fira Code'", "monospace"],
        sans: ["'Inter'", "-apple-system", "BlinkMacSystemFont", "sans-serif"],
      },
    },
  },
  plugins: [],
};
