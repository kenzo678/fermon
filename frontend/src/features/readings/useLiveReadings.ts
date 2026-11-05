import { useQueryClient } from "@tanstack/react-query";
import type { QueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import type { Measurement, Reading, Tank } from "../../shared/api";
import { createReconnectingSocket, useSocketFactory, wsUrlFor } from "../../shared/realtime";
import type { SocketStatus } from "../../shared/realtime";
import { tankKeys } from "../tanks/api";
import { readingKeys } from "./api";

export type LiveStatus = "live" | "reconnecting" | "offline";

/** At most one aggregated refetch per tank in this window; charts do not need every reading. */
export const AGGREGATED_REFRESH_MS = 15_000;

/** Reconnects within this window share one tank-list invalidation (a backend restart reopens every socket together). */
export const LIST_INVALIDATION_DEBOUNCE_MS = 250;

const MEASUREMENTS: readonly string[] = ["temperature", "pressure", "alcohol"];

function parseReading(data: unknown, tankId: string): Reading | null {
  if (typeof data !== "object" || data === null) return null;
  const r = data as Partial<Reading>;
  if (
    r.tank_id !== tankId ||
    typeof r.measurement !== "string" ||
    !MEASUREMENTS.includes(r.measurement) ||
    typeof r.value !== "number" ||
    typeof r.recorded_at !== "string" ||
    Number.isNaN(Date.parse(r.recorded_at))
  ) {
    return null;
  }
  return r as Reading;
}

/** Returns the tank with the reading applied, or the same object when it is not newer. */
function applyReading(tank: Tank, reading: Reading): Tank {
  const current = tank.latest[reading.measurement as Measurement];
  if (current !== null && Date.parse(reading.recorded_at) <= Date.parse(current.recorded_at)) {
    return tank;
  }
  return { ...tank, latest: { ...tank.latest, [reading.measurement]: reading } };
}

function updateCaches(queryClient: QueryClient, reading: Reading): void {
  queryClient.setQueryData<Tank[]>(tankKeys.list(), (tanks) => {
    if (tanks === undefined) return undefined;
    let changed = false;
    const next = tanks.map((tank) => {
      if (tank.id !== reading.tank_id) return tank;
      const updated = applyReading(tank, reading);
      changed ||= updated !== tank;
      return updated;
    });
    return changed ? next : tanks;
  });
  queryClient.setQueryData<Tank>(tankKeys.detail(reading.tank_id), (tank) =>
    tank === undefined ? undefined : applyReading(tank, reading),
  );
}

const TERMINAL: readonly SocketStatus[] = ["forbidden", "not_found"];

/**
 * Terminal sockets (unknown tank, forbidden origin) are ignored so one bad tank does not mask
 * the live ones; with no non-terminal socket left there is nothing to stream from.
 */
export function aggregateStatus(ids: string[], statuses: Record<string, SocketStatus>): LiveStatus {
  const active = ids
    .map((id) => statuses[id] ?? "connecting")
    .filter((status) => !TERMINAL.includes(status));
  if (active.length === 0) return "offline";
  if (active.every((s) => s === "open")) return "live";
  if (active.some((s) => s === "connecting" || s === "reconnecting")) return "reconnecting";
  return "offline";
}

/**
 * Container hook: keeps one reconnecting WebSocket per tank and folds readings into the
 * TanStack Query caches. The stream is best-effort, so every reconnect also invalidates the
 * REST-backed queries to backfill what was missed.
 */
export function useLiveReadings(tankIds: string[]): LiveStatus {
  const queryClient = useQueryClient();
  const socketFactory = useSocketFactory();
  const [statuses, setStatuses] = useState<Record<string, SocketStatus>>({});

  // A sorted, de-duplicated key keeps sockets stable across renders that pass a new array.
  const idsKey = JSON.stringify([...new Set(tankIds)].sort());
  const ids = useMemo(() => JSON.parse(idsKey) as string[], [idsKey]);

  useEffect(() => {
    const lastRefresh = new Map<string, number>();
    const pending = new Map<string, ReturnType<typeof setTimeout>>();

    const refreshAggregated = (tankId: string) => {
      lastRefresh.set(tankId, Date.now());
      void queryClient.invalidateQueries({ queryKey: [...readingKeys.all, "aggregated", tankId] });
    };

    const scheduleAggregatedRefresh = (tankId: string) => {
      if (pending.has(tankId)) return;
      const wait = (lastRefresh.get(tankId) ?? -Infinity) + AGGREGATED_REFRESH_MS - Date.now();
      if (wait <= 0) {
        refreshAggregated(tankId);
        return;
      }
      pending.set(
        tankId,
        setTimeout(() => {
          pending.delete(tankId);
          refreshAggregated(tankId);
        }, wait),
      );
    };

    let listTimer: ReturnType<typeof setTimeout> | undefined;
    const scheduleListInvalidation = () => {
      if (listTimer !== undefined) return;
      listTimer = setTimeout(() => {
        listTimer = undefined;
        // Do not restart a list fetch that is already in flight.
        void queryClient.invalidateQueries({ queryKey: tankKeys.list() }, { cancelRefetch: false });
      }, LIST_INVALIDATION_DEBOUNCE_MS);
    };

    const sockets = ids.map((tankId) =>
      createReconnectingSocket({
        url: wsUrlFor(`/ws/tanks/${encodeURIComponent(tankId)}`),
        socketFactory,
        onStatus: (status) => setStatuses((prev) => ({ ...prev, [tankId]: status })),
        onOpen: (isReconnect) => {
          if (!isReconnect) return;
          scheduleListInvalidation();
          void queryClient.invalidateQueries({ queryKey: tankKeys.detail(tankId) });
          scheduleAggregatedRefresh(tankId);
        },
        onMessage: (data) => {
          const reading = parseReading(data, tankId);
          if (reading === null) return;
          updateCaches(queryClient, reading);
          scheduleAggregatedRefresh(tankId);
        },
      }),
    );

    return () => {
      sockets.forEach((socket) => socket.close());
      pending.forEach((timer) => clearTimeout(timer));
      clearTimeout(listTimer);
    };
  }, [ids, queryClient, socketFactory]);

  return aggregateStatus(ids, statuses);
}
