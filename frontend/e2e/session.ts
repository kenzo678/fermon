import type { APIRequestContext, PlaywrightWorkerArgs } from "@playwright/test";

/** Where the browser reaches the app; the API is behind the same origin at `/api` (see vite.config.ts). */
export const BASE_URL = process.env.E2E_BASE_URL ?? "http://frontend-e2e:5173";
export const API_URL = `${BASE_URL}/api`;

/** The admin created by the `e2e-admin` compose service (docker-compose.yml): same defaults. */
export const ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL ?? "e2e-admin@example.com";
export const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? "e2e-admin-password";
export const ADMIN_NAME = "E2E Admin";

/** Session cookie of the admin, saved once by the global setup and reused by every spec. */
export const AUTH_FILE = "e2e/.auth/admin.json";

/** The CSRF header the API demands on every unsafe request. */
export const CSRF_HEADERS = { "X-Requested-With": "fermon" };

/** An API client signed in as the admin, for setup and cleanup outside a test's own fixtures. */
export function adminApiContext(playwright: PlaywrightWorkerArgs["playwright"]): Promise<APIRequestContext> {
  return playwright.request.newContext({
    baseURL: BASE_URL,
    extraHTTPHeaders: CSRF_HEADERS,
    storageState: AUTH_FILE,
  });
}
