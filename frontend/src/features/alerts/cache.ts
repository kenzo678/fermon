import type { QueryClient } from "@tanstack/react-query";
import type { Alert } from "../../shared/api";
import { alertKeys } from "./api";
import type { AlertFilters } from "./api";
import { UNRESOLVED } from "./format";

/** Mirrors the server-side filtering of `GET /alerts`, so cached lists can be patched locally. */
export function matchesFilters(alert: Alert, filters: AlertFilters): boolean {
  if (filters.tank_id !== undefined && alert.tank_id !== filters.tank_id) return false;
  if (filters.batch_id !== undefined && alert.batch_id !== filters.batch_id) return false;
  if (filters.kind !== undefined && alert.kind !== filters.kind) return false;
  return (filters.status ?? UNRESOLVED).includes(alert.status);
}

const openedAt = (alert: Alert) => Date.parse(alert.opened_at);

/** Returns the same array when nothing changes, so React Query keeps its structural sharing. */
function patchList(list: Alert[], alert: Alert, filters: AlertFilters): Alert[] {
  const index = list.findIndex((item) => item.id === alert.id);
  const existing = list[index];
  if (existing !== undefined && alert.version < existing.version) return list;
  const matches = matchesFilters(alert, filters);
  if (existing !== undefined) {
    if (!matches) return list.filter((item) => item.id !== alert.id);
    return list.map((item) => (item.id === alert.id ? alert : item));
  }
  if (!matches) return list;
  // Newest first, like the API.
  const at = list.findIndex((item) => openedAt(item) < openedAt(alert));
  const next = at === -1 ? [...list, alert] : [...list.slice(0, at), alert, ...list.slice(at)];
  return filters.limit === undefined ? next : next.slice(0, filters.limit);
}

/** Folds one alert revision into every cached alert list (insert, replace or drop by filters). */
export function applyAlert(queryClient: QueryClient, alert: Alert): void {
  for (const [key, list] of queryClient.getQueriesData<Alert[]>({ queryKey: alertKeys.lists() })) {
    if (list === undefined) continue;
    const filters = key[2] as AlertFilters;
    const next = patchList(list, alert, filters);
    if (next !== list) queryClient.setQueryData(key, next);
  }
}
