import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  base: process.env.GITHUB_PAGES === "true" ? "/IntegrityShield/" : "/",
  // For GitHub Pages, use GCP Cloud Run backend
  define: process.env.GITHUB_PAGES === "true" ? {
    "import.meta.env.VITE_API_BASE_URL": JSON.stringify("https://integrityshield-backend-374966265394.us-central1.run.app/api")
  } : {},
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
        target: process.env.VITE_API_BASE_URL?.replace(/\/api\/?$/, "") || "https://integrityshield-backend-374966265394.us-central1.run.app",
        changeOrigin: true,
        ws: true,
        rewrite: (path) => path.replace(/^\/api/, '/api'),
      },
      "/developer": {
        target: process.env.VITE_API_BASE_URL?.replace(/\/api\/?$/, "") || "https://integrityshield-backend-374966265394.us-central1.run.app",
        changeOrigin: true,
        ws: true,
      },
      "/ws": {
        target: process.env.VITE_API_BASE_URL?.replace(/\/api\/?$/, "").replace('https://', 'wss://') || "wss://integrityshield-backend-374966265394.us-central1.run.app",
        ws: true
      }
    }
  }
});
