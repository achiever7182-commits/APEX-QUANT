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
          bg: "#09090b", // zinc-950
          surface: "#18181b", // zinc-900
          card: "#27272a", // zinc-800
          elevated: "#3f3f46", // zinc-700
          border: "#27272a", // zinc-800
          borderBright: "#3f3f46", // zinc-700
          textPrimary: "#fafafa", // zinc-50
          textSecondary: "#a1a1aa", // zinc-400
          textMuted: "#71717a", // zinc-500
          
          // Re-map semantic colors to grayscale/subtle tones
          cyan: "#d4d4d8", // light gray instead of bright cyan
          cyanMuted: "rgba(212, 212, 216, 0.1)",
          blue: "#d4d4d8", // mapped to gray
          bull: "#e4e4e7", // white/light gray for positive
          bullMuted: "rgba(228, 228, 231, 0.1)",
          bear: "#71717a", // darker gray for negative
          bearMuted: "rgba(113, 113, 122, 0.1)",
          warn: "#a1a1aa", // gray for warn
          warnMuted: "rgba(161, 161, 170, 0.1)",
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
