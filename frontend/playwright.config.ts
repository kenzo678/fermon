import { defineConfig, devices } from "@playwright/test";

import { AUTH_FILE, BASE_URL, CSRF_HEADERS } from "./e2e/session";

export default defineConfig({
  testDir: "./e2e",
  // Waits until the simulator has produced readings for every expected tank.
  globalSetup: "./e2e/global-setup.ts",
  outputDir: "./test-results",
  reporter: "list",
  retries: 0,
  fullyParallel: true,
  use: {
    // Signed in as the admin by the global setup; specs about logging in opt out with an empty state.
    storageState: AUTH_FILE,
    // The API refuses unsafe requests without it; the app sends it itself, API helpers rely on this.
    extraHTTPHeaders: CSRF_HEADERS,
    // The `frontend-e2e` service is built to call the API at an address the browser can reach.
    baseURL: BASE_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "desktop-chromium", use: { ...devices["Desktop Chrome"] }, testIgnore: /thesis-flow\.spec\.ts/ },
    {
      name: "mobile",
      use: { ...devices["Pixel 7"] },
      // These specs mutate shared tank state (one active batch per tank): desktop only, to avoid races.
      testIgnore: /batches-alerts\.spec\.ts|thesis-flow\.spec\.ts/,
    },
    {
      // Uses tank-1 and renames it, which would break the other specs reading it by id, so it runs alone
      // once they are done (a failure there skips it), and only on desktop.
      name: "thesis-flow",
      use: { ...devices["Desktop Chrome"] },
      testMatch: /thesis-flow\.spec\.ts/,
      dependencies: ["desktop-chromium", "mobile"],
    },
  ],
});
