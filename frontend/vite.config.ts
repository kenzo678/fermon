import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { configDefaults, defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    // Compose service names used by the e2e stack (Vite rejects unknown Host headers).
    allowedHosts: ["frontend", "frontend-e2e"],
    // Bind mounts on Docker do not forward fs events reliably.
    watch: { usePolling: true },
  },
  test: {
    exclude: [...configDefaults.exclude, "e2e/**"],
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    // Pin the API base so tests never depend on the developer's VITE_API_URL.
    env: { VITE_API_URL: "http://api.test" },
  },
});
