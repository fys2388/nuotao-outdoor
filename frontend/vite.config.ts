import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Nuotao AI OS console — Vite configuration (placeholder for M0).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});