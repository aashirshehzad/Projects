import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The React dev server proxies /api/* to the FastAPI backend on :8000,
// so the browser never has to deal with CORS.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
