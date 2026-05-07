import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const backendProxyTarget = process.env.VITE_BACKEND_PROXY_TARGET ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    allowedHosts: true,
    host: "0.0.0.0",
    port: 5173,
    proxy: {
      "/api": {
        changeOrigin: true,
        target: backendProxyTarget
      }
    }
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts"
  }
});
