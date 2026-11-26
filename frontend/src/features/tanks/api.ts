import { apiGet, apiSend } from "../../shared/api";
import type { Tank } from "../../shared/api";

export const tankKeys = {
  all: ["tanks"] as const,
  list: () => [...tankKeys.all, "list"] as const,
  detail: (tankId: string) => [...tankKeys.all, "detail", tankId] as const,
};

export function fetchTanks(signal?: AbortSignal): Promise<Tank[]> {
  return apiGet<Tank[]>("/tanks", { signal });
}

export function fetchTank(tankId: string, signal?: AbortSignal): Promise<Tank> {
  return apiGet<Tank>(`/tanks/${encodeURIComponent(tankId)}`, { signal });
}

/** `null` clears the display name, so the tank shows its id again. Admin only. */
export function renameTank(tankId: string, displayName: string | null): Promise<Tank> {
  return apiSend<Tank>("PATCH", `/tanks/${encodeURIComponent(tankId)}`, { display_name: displayName });
}
