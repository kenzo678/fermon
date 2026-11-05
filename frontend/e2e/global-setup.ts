import { TANK_IDS } from "./tanks";

const API_URL = process.env.E2E_API_URL ?? "http://api:8000";
const TIMEOUT_MS = 90_000;

interface TankSummary {
  id: string;
  latest: Record<string, unknown>;
}

/** The tests run against a live stack: fail fast with a clear message if it isn't ready. */
export default async function globalSetup(): Promise<void> {
  const deadline = Date.now() + TIMEOUT_MS;
  let last = "no response yet";
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${API_URL}/tanks`);
      if (response.ok) {
        const tanks = (await response.json()) as TankSummary[];
        const ready = TANK_IDS.every((id) =>
          tanks.some((t) => t.id === id && Object.values(t.latest).some((r) => r !== null)),
        );
        if (ready) return;
        last = `tanks so far: ${tanks.map((t) => t.id).join(", ") || "none"}`;
      } else {
        last = `GET /tanks -> ${response.status}`;
      }
    } catch (error) {
      last = String(error);
    }
    await new Promise((resolve) => setTimeout(resolve, 2_000));
  }
  throw new Error(
    `Stack not ready after ${TIMEOUT_MS / 1000}s (${last}). Apply migrations and start the simulator.`,
  );
}
