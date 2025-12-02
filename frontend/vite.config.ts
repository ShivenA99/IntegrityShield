import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  base: process.env.GITHUB_PAGES === "true" ? "/fairtestai_-llm-assessment-vulnerability-simulator-main/" : "/",
  build: {
    outDir: process.env.GITHUB_PAGES === "true" ? "../docs" : "dist",
    emptyOutDir: true,
  },
  resolve: {
    alias: {
      "@components": path.resolve(__dirname, "src/components"),
      "@hooks": path.resolve(__dirname, "src/hooks"),
      "@services": path.resolve(__dirname, "src/services"),
      "@contexts": path.resolve(__dirname, "src/contexts"),
      "@pages": path.resolve(__dirname, "src/pages"),
      "@styles": path.resolve(__dirname, "src/styles"),
      "@constants": path.resolve(__dirname, "src/constants"),
      "@data": path.resolve(__dirname, "src/data"),
      "@layout": path.resolve(__dirname, "src/layout"),
      "@utils": path.resolve(__dirname, "src/utils"),
    }
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        ws: true,
      },
      "/developer": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        ws: true,
      },
      "/ws": {
        target: "ws://127.0.0.1:8000",
        ws: true
      }
    }
  }
});
