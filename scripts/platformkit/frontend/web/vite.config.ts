import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server proxies /api and /health to the FastAPI decision-support service
// (scripts.platformkit.frontend.serve) which defaults to port 8098.
// Override the target with VITE_API_TARGET if you run serve.py on another port.
const API_TARGET = process.env.VITE_API_TARGET ?? "http://127.0.0.1:8098";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    port: 5174,
    proxy: {
      "/api": { target: API_TARGET, changeOrigin: true },
      "/health": { target: API_TARGET, changeOrigin: true },
    },
  },
  // dist/ is emitted relative to this dir; FastAPI can later StaticFiles-mount it.
  build: { outDir: "dist", sourcemap: false },
});
