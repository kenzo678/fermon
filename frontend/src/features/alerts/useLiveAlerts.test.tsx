import { QueryClientProvider, QueryObserver } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { API_URL } from "../../shared/api";
import type { Alert } from "../../shared/api";
import { RealtimeProvider } from "../../shared/realtime";
import { createFakeSocketHub } from "../../test/fakeSocket";
import { makeAlert, makeTank } from "../../test/fixtures";
import { createTestQueryClient } from "../../test/renderWithProviders";
import { server } from "../../test/server";
import { tankKeys } from "../tanks/api";
import { alertKeys } from "./api";
import { applyAlert, matchesFilters } from "./cache";
import { TANKS_REFRESH_DEBOUNCE_MS, useLiveAlerts, parseAlertEvent } from "./useLiveAlerts";

const event = (alert: Alert) => JSON.stringify({ type: "alert", alert });

function setup() {
  const hub = createFakeSocketHub();
  const queryClient = createTestQueryClient();
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <RealtimeProvider socketFactory={hub.factory}>{children}</RealtimeProvider>
    </QueryClientProvider>
  );
  const view = renderHook(() => useLiveAlerts(), { wrapper });
  return { hub, queryClient, ...view };
}

afterEach(() => vi.useRealTimers());

describe("matchesFilters", () => {
  it("treats a missing status filter as unresolved", () => {
    expect(matchesFilters(makeAlert({ status: "open" }), {})).toBe(true);
    expect(matchesFilters(makeAlert({ status: "acknowledged" }), {})).toBe(true);
    expect(matchesFilters(makeAlert({ status: "resolved" }), {})).toBe(false);
  });

  it("checks tank, batch, kind and explicit statuses", () => {
    const alert = makeAlert({ status: "resolved" });
    expect(matchesFilters(alert, { status: ["resolved"] })).toBe(true);
    expect(matchesFilters(alert, { status: ["resolved"], tank_id: "tank-2" })).toBe(false);
    expect(matchesFilters(alert, { status: ["resolved"], batch_id: "other" })).toBe(false);
    expect(matchesFilters(alert, { status: ["resolved"], kind: "silent_sensor" })).toBe(false);
  });
});

describe("applyAlert", () => {
  it("keeps lists newest first and honours the limit", () => {
    const queryClient = createTestQueryClient();
    const key = alertKeys.list({ limit: 2 });
    const older = makeAlert({ id: "old", opened_at: "2026-03-01T10:00:00Z" });
    const newer = makeAlert({ id: "new", opened_at: "2026-03-01T11:00:00Z" });
    queryClient.setQueryData<Alert[]>(key, [newer, older]);
    applyAlert(queryClient, makeAlert({ id: "newest", opened_at: "2026-03-01T12:00:00Z" }));
    expect(queryClient.getQueryData<Alert[]>(key)?.map((a) => a.id)).toEqual(["newest", "new"]);
  });
});

describe("useLiveAlerts cache updates", () => {
  it("inserts an opened alert into matching lists only", () => {
    const { hub, queryClient } = setup();
    const all = alertKeys.list({});
    const mine = alertKeys.list({ tank_id: "tank-1" });
    const other = alertKeys.list({ tank_id: "tank-2" });
    queryClient.setQueryData<Alert[]>(all, []);
    queryClient.setQueryData<Alert[]>(mine, []);
    queryClient.setQueryData<Alert[]>(other, []);
    const socket = hub.latest("/ws/alerts");
    act(() => socket.open());
    act(() => socket.message(event(makeAlert())));

    expect(queryClient.getQueryData<Alert[]>(all)).toHaveLength(1);
    expect(queryClient.getQueryData<Alert[]>(mine)).toHaveLength(1);
    expect(queryClient.getQueryData<Alert[]>(other)).toHaveLength(0);
  });

  it("replaces an acknowledged alert in place", () => {
    const { hub, queryClient } = setup();
    const key = alertKeys.list({});
    queryClient.setQueryData<Alert[]>(key, [makeAlert({ id: "a2", opened_at: "2026-03-01T13:00:00Z" }), makeAlert()]);
    const socket = hub.latest("/ws/alerts");
    act(() =>
      socket.message(event(makeAlert({ status: "acknowledged", acknowledged_at: "2026-03-01T12:05:00Z", version: 2 }))),
    );
    const list = queryClient.getQueryData<Alert[]>(key)!;
    expect(list.map((a) => [a.id, a.status])).toEqual([
      ["a2", "open"],
      ["a1", "acknowledged"],
    ]);
  });

  it("removes a resolved alert from unresolved lists and adds it to resolved ones", () => {
    const { hub, queryClient } = setup();
    const unresolved = alertKeys.list({});
    const resolved = alertKeys.list({ status: ["resolved"] });
    queryClient.setQueryData<Alert[]>(unresolved, [makeAlert()]);
    queryClient.setQueryData<Alert[]>(resolved, []);
    const socket = hub.latest("/ws/alerts");
    act(() =>
      socket.message(event(makeAlert({ status: "resolved", resolved_at: "2026-03-01T12:20:00Z", version: 3 }))),
    );
    expect(queryClient.getQueryData<Alert[]>(unresolved)).toEqual([]);
    expect(queryClient.getQueryData<Alert[]>(resolved)?.[0]).toMatchObject({ id: "a1", status: "resolved" });
  });

  it("ignores an event older than the cached version", () => {
    const { hub, queryClient } = setup();
    const key = alertKeys.list({});
    const current = makeAlert({ status: "acknowledged", version: 2 });
    queryClient.setQueryData<Alert[]>(key, [current]);
    const socket = hub.latest("/ws/alerts");
    act(() => socket.message(event(makeAlert({ version: 1 }))));
    expect(queryClient.getQueryData<Alert[]>(key)).toEqual([current]);
  });

  it("drops malformed and foreign messages without breaking later ones", () => {
    const { hub, queryClient } = setup();
    const key = alertKeys.list({});
    queryClient.setQueryData<Alert[]>(key, []);
    const socket = hub.latest("/ws/alerts");
    act(() => {
      socket.message(JSON.stringify({ type: "other", alert: makeAlert() }));
      socket.message(JSON.stringify({ type: "alert", alert: { id: 3 } }));
      socket.message(event(makeAlert()));
    });
    expect(queryClient.getQueryData<Alert[]>(key)).toHaveLength(1);
  });
});

describe("useLiveAlerts tank counters", () => {
  function countingTanks() {
    const requests = { count: 0 };
    server.use(
      http.get(`${API_URL}/tanks`, () => {
        requests.count += 1;
        return HttpResponse.json([makeTank("tank-1", { open_alerts: 1 })]);
      }),
    );
    return requests;
  }

  it("refetches the tank queries once, debounced, when alerts open or resolve", async () => {
    const requests = countingTanks();
    const { hub, queryClient } = setup();
    // An observer keeps the tank list active so invalidation refetches it.
    queryClient.setQueryData(tankKeys.list(), [makeTank("tank-1")]);
    const unsubscribe = new QueryObserver(queryClient, {
      queryKey: tankKeys.list(),
      queryFn: () => fetch(`${API_URL}/tanks`).then((r) => r.json()),
      staleTime: Infinity,
    }).subscribe(() => {});
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    const socket = hub.latest("/ws/alerts");
    act(() => {
      socket.message(event(makeAlert({ id: "a1" })));
      socket.message(event(makeAlert({ id: "a2" })));
    });
    expect(requests.count).toBe(0);
    await act(async () => {
      vi.advanceTimersByTime(TANKS_REFRESH_DEBOUNCE_MS);
    });
    vi.useRealTimers();
    await waitFor(() => expect(requests.count).toBe(1));
    unsubscribe();
  });

  it("does not refetch the tanks for an acknowledgement (the count does not change)", async () => {
    const requests = countingTanks();
    const { hub, queryClient } = setup();
    queryClient.setQueryData(tankKeys.list(), [makeTank("tank-1")]);
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    act(() => hub.latest("/ws/alerts").message(event(makeAlert({ status: "acknowledged", version: 2 }))));
    await act(async () => {
      vi.advanceTimersByTime(TANKS_REFRESH_DEBOUNCE_MS * 2);
    });
    expect(requests.count).toBe(0);
  });
});

describe("useLiveAlerts connection", () => {
  it("opens one socket to /ws/alerts and reports its status", () => {
    const { hub, result } = setup();
    expect(hub.sockets).toHaveLength(1);
    expect(hub.sockets[0]?.url).toMatch(/\/ws\/alerts$/);
    expect(result.current).toBe("reconnecting");
    act(() => hub.latest("/ws/alerts").open());
    expect(result.current).toBe("live");
    act(() => hub.latest("/ws/alerts").serverClose());
    expect(result.current).toBe("reconnecting");
  });

  it("is offline after a terminal close", () => {
    const { hub, result } = setup();
    act(() => hub.latest("/ws/alerts").serverClose(4403));
    expect(result.current).toBe("offline");
  });

  it("closes the socket on unmount", () => {
    const { hub, unmount } = setup();
    unmount();
    expect(hub.sockets[0]?.closedByClient).toBe(true);
  });

  it("backfills alert lists and tanks on reopen, not on the first open", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    const { hub, queryClient } = setup();
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    act(() => hub.latest("/ws/alerts").open());
    expect(invalidate).not.toHaveBeenCalled();

    act(() => hub.latest("/ws/alerts").serverClose());
    await act(async () => {
      vi.advanceTimersByTime(1_000);
    });
    act(() => hub.latest("/ws/alerts").open());
    await act(async () => {
      vi.advanceTimersByTime(TANKS_REFRESH_DEBOUNCE_MS);
    });
    const keys = invalidate.mock.calls.map(([filters]) => filters?.queryKey);
    expect(keys).toContainEqual(alertKeys.lists());
    expect(keys).toContainEqual(tankKeys.all);
  });
});

describe("parseAlertEvent", () => {
  const event = (alert: Record<string, unknown>) => ({ type: "alert", alert });

  it("accepts a well-formed alert event", () => {
    expect(parseAlertEvent(event({ ...makeAlert() }))).not.toBeNull();
  });

  it.each([
    ["details missing", { details: undefined }],
    ["details not an object", { details: "x" }],
    ["acknowledged_at not a string or null", { acknowledged_at: 5 }],
    ["resolved_at unparseable", { resolved_at: "garbage" }],
  ])("rejects an event with %s instead of crashing the render", (_case, patch) => {
    expect(parseAlertEvent(event({ ...makeAlert(), ...patch }))).toBeNull();
  });
});
