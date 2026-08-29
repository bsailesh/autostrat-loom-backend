import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The app calls the API directly using VITE_API_BASE (see src/api.js), matching
// the convention the existing marketing index.html already uses. No dev proxy —
// the FastAPI backend's CORS_ORIGINS already permits browser calls.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
});
