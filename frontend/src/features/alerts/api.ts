import { apiGet, apiSend } from "../../shared/api";
import type { Alert, AlertKind, AlertStatus } from "../../shared/api";

export interface AlertFilters {
  tank_id?: string;
  batch_id?: string;
  kind?: AlertKind;
  /** Repeatable; when omitted the API returns the unresolved alerts (open + acknowledged). */
  status?: AlertStatus[];
  limit?: number;
}

export const alertKeys = {
  all: ["alerts"] as const,
  lists: () => [...alertKeys.all, "list"] as const,
  list: (filters: AlertFilters) => [...alertKeys.lists(), filters] as const,
};

export function fetchAlerts(filters: AlertFilters, signal?: AbortSignal): Promise<Alert[]> {
  return apiGet<Alert[]>("/alerts", { params: { ...filters }, signal });
}

/** `version` makes the server reject the acknowledgement if the alert changed since it was read. */
export function acknowledgeAlert(alert: Pick<Alert, "id" | "version">): Promise<Alert> {
  return apiSend<Alert>("POST", `/alerts/${encodeURIComponent(alert.id)}/acknowledge`, {
    version: alert.version,
  });
}
