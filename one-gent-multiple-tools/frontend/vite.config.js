import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The React dev server proxies /api/* to the FastAPI backend, so the browser
// never has to deal with CORS. Override the port with BACKEND_PORT if 8000
// is already taken by another local project (e.g. `BACKEND_PORT=8010 npm run dev`).
const backendPort = process.env.BACKEND_PORT || "8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": `http://localhost:${backendPort}`,
    },
  },
});
