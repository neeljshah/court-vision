import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

// Dev server proxies /api -> the FastAPI live board (port 8090) so the SPA
// consumes the SAME /api/board contract with no CORS juggling. The JSON
// contract is owned by another session; this app never mutates it.
const BOARD_API = process.env.BOARD_API ?? "http://127.0.0.1:8090";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
  },
  server: {
    port: 5174,
    proxy: {
      "/api": { target: BOARD_API, changeOrigin: true },
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
