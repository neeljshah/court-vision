/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // All driven by CSS variables in index.css (light + dark + system).
        bg: "rgb(var(--bg) / <alpha-value>)",
        surface: "rgb(var(--surface) / <alpha-value>)",
        surface2: "rgb(var(--surface2) / <alpha-value>)",
        line: "rgb(var(--line) / <alpha-value>)",
        txt: "rgb(var(--txt) / <alpha-value>)",
        muted: "rgb(var(--muted) / <alpha-value>)",
        accent: "rgb(var(--accent) / <alpha-value>)",
        model: "rgb(var(--model) / <alpha-value>)",
        market: "rgb(var(--market) / <alpha-value>)",
        live: "rgb(var(--live) / <alpha-value>)",
        win: "rgb(var(--win) / <alpha-value>)",
        draw: "rgb(var(--draw) / <alpha-value>)",
      },
      fontFamily: {
        sans: [
          "-apple-system", "BlinkMacSystemFont", "Segoe UI", "Roboto",
          "Helvetica", "Arial", "sans-serif",
        ],
      },
      fontVariantNumeric: { tabular: "tabular-nums" },
      keyframes: {
        pulse2: { "0%,100%": { opacity: "1" }, "50%": { opacity: "0.3" } },
        shimmer: { "100%": { transform: "translateX(100%)" } },
        "fade-in": { from: { opacity: "0" }, to: { opacity: "1" } },
        flash: {
          "0%": { backgroundColor: "rgb(var(--accent) / 0.20)" },
          "100%": { backgroundColor: "transparent" },
        },
      },
      animation: {
        "live-pulse": "pulse2 1.4s ease-in-out infinite",
        shimmer: "shimmer 1.6s infinite",
        "fade-in": "fade-in 0.18s ease-out",
        "score-flash": "flash 1.6s ease-out",
      },
    },
  },
  plugins: [],
};
