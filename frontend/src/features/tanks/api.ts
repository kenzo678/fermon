import { apiGet } from "../../shared/api";
import type { Tank } from "../../shared/api";

export const tankKeys = {
  all: ["tanks"] as const,
  list: () => [...tankKeys.all, "list"] as const,
};

export function fetchTanks(signal?: AbortSignal): Promise<Tank[]> {
  return apiGet<Tank[]>("/tanks", { signal });
}
