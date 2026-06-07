import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        tier: {
          s: "#fbbf24",   // gold
          a: "#22c55e",   // green
          b: "#94a3b8",   // slate
          c: "#475569",
        },
        bg: {
          base: "#0a0a0f",
          panel: "#13131a",
          subtle: "#1c1c25",
        },
      },
      fontFamily: {
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
};
export default config;
