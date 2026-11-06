import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";

// In development the API runs separately on :8000. The proxy passes paths
// through unchanged, so /api/... reaches the same route it does in the
// container, where one process serves both.
export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/healthz": "http://127.0.0.1:8000",
      "/readyz": "http://127.0.0.1:8000",
    },
  },
});
