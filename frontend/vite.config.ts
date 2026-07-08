import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      // Dev proxy: forward /api/* → backend, stripping the /api prefix.
      // This sidesteps the missing CORS headers on the backend — all
      // requests from the browser are same-origin (localhost:5173).
      // In production, set VITE_API_BASE_URL to the real backend URL
      // and serve through a reverse proxy that adds CORS headers.
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          "vendor-react": ["react", "react-dom", "react-router-dom"],
          "vendor-query": ["@tanstack/react-query"],
          "vendor-motion": ["framer-motion"],
          "vendor-ui": ["lucide-react", "sonner", "clsx", "tailwind-merge"],
        },
      },
    },
  },
});

