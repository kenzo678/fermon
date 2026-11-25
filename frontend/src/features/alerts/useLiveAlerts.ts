import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import type { Alert } from "../../shared/api";
import { createReconnectingSocket, useSocketFactory, wsUrlFor } from "../../shared/realtime";
import type { SocketStatus } from "../../shared/realtime";
import { refreshSession } from "../auth/api";
import { tankKeys } from "../tanks/api";
import { alertKeys } from "./api";
import { applyAlert } from "./cache";
import { KIND_ORDER, STATUS_ORDER } from "./format";

export type LiveAlertsStatus = "live" | "reconnecting" | "offline";

/** Alerts that open or resolve together (e.g. a finished batch) share one tank refetch. */
export const TANKS_REFRESH_DEBOUNCE_MS = 250;

const isOptionalTimestamp = (value: unknown): boolean =>
  value === null || (typeof value === "string" && !Number.isNaN(Date.parse(value)));

/** Validates a socket message before it reaches the cache; malformed events are dropped, not rendered. */
export function parseAlertEvent(data: unknown): Alert | null {
  if (typeof data !== "object" || data === null) return null;
  const { type, alert } = data as { type?: unknown; alert?: Partial<Alert> };
  if (type !== "alert" || typeof alert !== "object" || alert === null) return null;
  if (
    typeof alert.id !== "string" ||
    typeof alert.tank_id !== "string" ||
    typeof alert.version !== "number" ||
    typeof alert.opened_at !== "string" ||
    Number.isNaN(Date.parse(alert.opened_at)) ||
    !STATUS_ORDER.includes(alert.status as Alert["status"]) ||
    !KIND_ORDER.includes(alert.kind as Alert["kind"]) ||
    typeof alert.details !== "object" ||
    alert.details === null ||
    Array.isArray(alert.details) ||
    !isOptionalTimestamp(alert.acknowledged_at) ||
    !isOptionalTimestamp(alert.resolved_at)
  ) {
    return null;
  }
  return alert as Alert;
}

const STATUS_MAP: Record<SocketStatus, LiveAlertsStatus> = {
  connecting: "reconnecting",
  open: "live",
  reconnecting: "reconnecting",
  closed: "offline",
  forbidden: "offline",
  unauthorized: "offline",
  not_found: "offline",
};

/**
 * Container hook: one reconnecting socket to `/ws/alerts` that folds every alert revision into
 * the cached alert lists. `open_alerts` on the tanks only changes when an alert opens or
 * resolves, so those events (debounced) refetch the tank queries; the stream is best-effort, so
 * every reconnect backfills both the alert lists and the tanks.
 */
export function useLiveAlerts(): LiveAlertsStatus {
  const queryClient = useQueryClient();
  const socketFactory = useSocketFactory();
  const [status, setStatus] = useState<SocketStatus>("connecting");

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    const scheduleTanksRefresh = () => {
      if (timer !== undefined) return;
      timer = setTimeout(() => {
        timer = undefined;
        void queryClient.invalidateQueries({ queryKey: tankKeys.all }, { cancelRefetch: false });
      }, TANKS_REFRESH_DEBOUNCE_MS);
    };

    const socket = createReconnectingSocket({
      url: wsUrlFor("/ws/alerts"),
      socketFactory,
      onStatus: (next) => {
        setStatus(next);
        // No (valid) session: let the session query find out and the route guard take over.
        if (next === "unauthorized") void refreshSession(queryClient).catch(() => undefined);
      },
      onOpen: (isReconnect) => {
        if (!isReconnect) return;
        void queryClient.invalidateQueries({ queryKey: alertKeys.lists() });
        scheduleTanksRefresh();
      },
      onMessage: (data) => {
        const alert = parseAlertEvent(data);
        if (alert === null) return;
        applyAlert(queryClient, alert);
        if (alert.status !== "acknowledged") scheduleTanksRefresh();
      },
    });

    return () => {
      socket.close();
      clearTimeout(timer);
    };
  }, [queryClient, socketFactory]);

  return STATUS_MAP[status];
}
