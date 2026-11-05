import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  // Waits until the simulator has produced readings for every expected tank.
  globalSetup: "./e2e/global-setup.ts",
  outputDir: "./test-results",
  reporter: "list",
  retries: 0,
  fullyParallel: true,
  use: {
    // The `frontend-e2e` service is built to call the API at an address the browser can reach.
    baseURL: process.env.E2E_BASE_URL ?? "http://frontend-e2e:5173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "desktop-chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile", use: { ...devices["Pixel 7"] } },
  ],
});
