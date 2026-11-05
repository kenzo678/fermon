/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    // Bind mounts on Docker do not forward fs events reliably.
    watch: { usePolling: true },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    // Pin the API base so tests never depend on the developer's VITE_API_URL.
    env: { VITE_API_URL: "http://api.test" },
  },
});
