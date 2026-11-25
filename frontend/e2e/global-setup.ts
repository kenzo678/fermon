import { request } from "@playwright/test";

import { ADMIN_EMAIL, ADMIN_PASSWORD, API_URL, AUTH_FILE, BASE_URL, CSRF_HEADERS } from "./session";
import { TANK_IDS } from "./tanks";

const TIMEOUT_MS = 90_000;

interface TankSummary {
  id: string;
  latest: Record<string, unknown>;
}

/**
 * The tests run against a live stack: fail fast with a clear message if it isn't ready. It also
 * signs in as the admin once and saves the session, so no spec has to log in unless it is about
 * logging in.
 */
export default async function globalSetup(): Promise<void> {
  const api = await request.newContext({ baseURL: BASE_URL, extraHTTPHeaders: CSRF_HEADERS });
  try {
    const login = await api.post(`${API_URL}/auth/login`, {
      data: { email: ADMIN_EMAIL, password: ADMIN_PASSWORD },
    });
    if (!login.ok()) {
      throw new Error(
        `Could not sign in as ${ADMIN_EMAIL} (${login.status()}). Run the e2e-admin service to create it ` +
          "(docker compose --profile e2e run --rm e2e-admin) and check E2E_ADMIN_PASSWORD.",
      );
    }
    await api.storageState({ path: AUTH_FILE });

    const deadline = Date.now() + TIMEOUT_MS;
    let last = "no response yet";
    while (Date.now() < deadline) {
      try {
        const response = await api.get(`${API_URL}/tanks`);
        if (response.ok()) {
          const tanks = (await response.json()) as TankSummary[];
          const ready = TANK_IDS.every((id) =>
            tanks.some((t) => t.id === id && Object.values(t.latest).some((r) => r !== null)),
          );
          if (ready) return;
          last = `tanks so far: ${tanks.map((t) => t.id).join(", ") || "none"}`;
        } else {
          last = `GET /tanks -> ${response.status()}`;
        }
      } catch (error) {
        last = String(error);
      }
      await new Promise((resolve) => setTimeout(resolve, 2_000));
    }
    throw new Error(
      `Stack not ready after ${TIMEOUT_MS / 1000}s (${last}). Apply migrations and start the simulator.`,
    );
  } finally {
    await api.dispose();
  }
}
