import { QueryClientProvider } from "@tanstack/react-query";
import { act, render, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { API_URL } from "../../shared/api";
import type { Tank } from "../../shared/api";
import { RealtimeProvider } from "../../shared/realtime";
import { createFakeSocketHub } from "../../test/fakeSocket";
import { makeReading, makeTank } from "../../test/fixtures";
import { createTestQueryClient } from "../../test/renderWithProviders";
import { server } from "../../test/server";
import { tankKeys } from "../tanks/api";
import { useTanksQuery } from "../tanks/useTanksQuery";
import { useTankQuery } from "../tanks/useTankQuery";
import { useAggregatedReadingsQuery } from "./useAggregatedReadingsQuery";
import { aggregateStatus, LIST_INVALIDATION_DEBOUNCE_MS, useLiveReadings } from "./useLiveReadings";
import type { LiveStatus } from "./useLiveReadings";
import type { SocketStatus } from "../../shared/realtime";

const wire = (tankId: string, value: number, recordedAt: string, measurement = "temperature") =>
  JSON.stringify({ ...makeReading(tankId, "temperature", value, recordedAt), measurement });

function setup(ids: string[]) {
  const hub = createFakeSocketHub();
  const queryClient = createTestQueryClient();
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <RealtimeProvider socketFactory={hub.factory}>{children}</RealtimeProvider>
    </QueryClientProvider>
  );
  const view = renderHook(({ tankIds }) => useLiveReadings(tankIds), {
    wrapper,
    initialProps: { tankIds: ids },
  });
  return { hub, queryClient, wrapper, ...view };
}

afterEach(() => vi.useRealTimers());

describe("useLiveReadings cache updates", () => {
  it("replaces the cached latest reading with a newer one, for that tank only", () => {
    const { hub, queryClient } = setup(["tank-1"]);
    queryClient.setQueryData<Tank[]>(tankKeys.list(), [makeTank("tank-1"), makeTank("tank-2")]);
    queryClient.setQueryData<Tank>(tankKeys.detail("tank-1"), makeTank("tank-1"));
    const socket = hub.latest("/ws/tanks/tank-1");
    act(() => socket.open());
    act(() => socket.message(wire("tank-1", 20.5, "2026-03-01T10:05:00Z")));

    const list = queryClient.getQueryData<Tank[]>(tankKeys.list())!;
    expect(list[0]?.latest.temperature?.value).toBe(20.5);
    expect(list[0]?.latest.pressure?.value).toBe(1.234);
    expect(list[1]?.latest.temperature?.value).toBe(18.46);
    expect(queryClient.getQueryData<Tank>(tankKeys.detail("tank-1"))?.latest.temperature?.value).toBe(20.5);
  });

  it("ignores older and duplicate readings", () => {
    const { hub, queryClient } = setup(["tank-1"]);
    queryClient.setQueryData<Tank[]>(tankKeys.list(), [makeTank("tank-1")]);
    const socket = hub.latest("/ws/tanks/tank-1");
    act(() => socket.open());
    act(() => socket.message(wire("tank-1", 99, "2026-03-01T09:00:00Z")));
    act(() => socket.message(wire("tank-1", 98, "2026-03-01T10:00:00Z")));
    expect(queryClient.getQueryData<Tank[]>(tankKeys.list())?.[0]?.latest.temperature?.value).toBe(18.46);
  });

  it("fills a measurement the tank never reported and ignores invalid payloads", () => {
    const { hub, queryClient } = setup(["tank-1"]);
    queryClient.setQueryData<Tank[]>(tankKeys.list(), [
      makeTank("tank-1", { latest: { temperature: null, pressure: null, alcohol: null } }),
    ]);
    const socket = hub.latest("/ws/tanks/tank-1");
    act(() => socket.open());
    act(() => socket.message(JSON.stringify({ hello: "world" })));
    act(() => socket.message(wire("tank-1", 7, "2026-03-01T10:00:00Z", "humidity")));
    expect(queryClient.getQueryData<Tank[]>(tankKeys.list())?.[0]?.latest.temperature).toBeNull();
    act(() => socket.message(wire("tank-1", 7, "2026-03-01T10:00:00Z")));
    expect(queryClient.getQueryData<Tank[]>(tankKeys.list())?.[0]?.latest.temperature?.value).toBe(7);
  });

  it("does not create a cache entry when nothing was loaded", () => {
    const { hub, queryClient } = setup(["tank-1"]);
    const socket = hub.latest("/ws/tanks/tank-1");
    act(() => socket.open());
    act(() => socket.message(wire("tank-1", 7, "2026-03-01T10:00:00Z")));
    expect(queryClient.getQueryData(tankKeys.list())).toBeUndefined();
  });
});

describe("useLiveReadings sockets", () => {
  it("opens one socket per id, follows id changes and closes everything on unmount", () => {
    const { hub, rerender, unmount } = setup(["a", "b"]);
    expect(hub.sockets.map((s) => s.url)).toEqual([
      `${API_URL.replace("http", "ws")}/ws/tanks/a`,
      `${API_URL.replace("http", "ws")}/ws/tanks/b`,
    ]);
    rerender({ tankIds: ["b", "a"] });
    expect(hub.sockets).toHaveLength(2);
    rerender({ tankIds: ["b", "c"] });
    // A changed id set reconnects every tank: the old sockets close, the new set opens.
    expect(hub.sockets).toHaveLength(4);
    expect(hub.sockets.slice(0, 2).every((s) => s.closedByClient)).toBe(true);
    expect(hub.sockets.slice(2).some((s) => s.closedByClient)).toBe(false);
    unmount();
    expect(hub.sockets.every((s) => s.closedByClient)).toBe(true);
  });

  it("aggregates connection status", () => {
    const { hub, result } = setup(["a", "b"]);
    expect(result.current).toBe("reconnecting");
    act(() => hub.latest("/a").open());
    expect(result.current).toBe("reconnecting");
    act(() => hub.latest("/b").open());
    expect(result.current).toBe("live");
    act(() => hub.latest("/a").serverClose(1006));
    expect(result.current).toBe("reconnecting");
  });

  it("reports offline for a terminal close and when there is nothing to watch", () => {
    const { hub, result } = setup(["a"]);
    act(() => hub.latest("/a").serverClose(4404));
    expect(result.current).toBe("offline");
    expect(setup([]).result.current).toBe("offline");
  });

  it("stays live when one tank is gone but another still streams", () => {
    const { hub, result } = setup(["a", "b"]);
    act(() => hub.latest("/a").open());
    act(() => hub.latest("/b").serverClose(4404));
    expect(result.current).toBe("live");
  });
});

describe("aggregateStatus", () => {
  const cases: [string, string[], Record<string, SocketStatus>, LiveStatus][] = [
    ["no ids", [], {}, "offline"],
    ["unknown socket counts as connecting", ["a"], {}, "reconnecting"],
    ["all open", ["a", "b"], { a: "open", b: "open" }, "live"],
    ["open + not_found", ["a", "b"], { a: "open", b: "not_found" }, "live"],
    ["open + forbidden", ["a", "b"], { a: "open", b: "forbidden" }, "live"],
    ["open + reconnecting", ["a", "b"], { a: "open", b: "reconnecting" }, "reconnecting"],
    ["connecting + not_found", ["a", "b"], { a: "connecting", b: "not_found" }, "reconnecting"],
    ["only terminal", ["a", "b"], { a: "not_found", b: "forbidden" }, "offline"],
    ["closed + terminal", ["a", "b"], { a: "closed", b: "not_found" }, "offline"],
    ["open + closed", ["a", "b"], { a: "open", b: "closed" }, "offline"],
  ];
  it.each(cases)("%s", (_name, ids, statuses, expected) => {
    expect(aggregateStatus(ids, statuses)).toBe(expected);
  });
});

describe("useLiveReadings backfill", () => {
  function Probe() {
    useTanksQuery();
    return null;
  }

  it("refetches the overview on reconnect but not on the first open", async () => {
    let calls = 0;
    server.use(
      http.get(`${API_URL}/tanks`, () => {
        calls += 1;
        return HttpResponse.json([makeTank("tank-1")]);
      }),
    );
    const { hub, wrapper } = setup(["tank-1"]);
    render(<Probe />, { wrapper });
    await waitFor(() => expect(calls).toBe(1));
    const socket = hub.latest("/tank-1");
    act(() => socket.open());
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(calls).toBe(1);

    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    act(() => socket.serverClose(1006));
    act(() => vi.advanceTimersByTime(1000));
    vi.useRealTimers();
    act(() => hub.latest("/tank-1").open());
    await waitFor(() => expect(calls).toBe(2));
  });
});

describe("useLiveReadings reconnect backfill of every cache", () => {
  function Probes() {
    useTanksQuery();
    useTankQuery("tank-1");
    useAggregatedReadingsQuery("tank-1", "24h");
    return null;
  }

  it("refetches the list, the tank detail and its aggregated readings on reconnect", async () => {
    const calls = { list: 0, detail: 0, aggregated: 0 };
    server.use(
      http.get(`${API_URL}/tanks`, () => {
        calls.list += 1;
        return HttpResponse.json([makeTank("tank-1")]);
      }),
      http.get(`${API_URL}/tanks/tank-1`, () => {
        calls.detail += 1;
        return HttpResponse.json(makeTank("tank-1"));
      }),
      http.get(`${API_URL}/tanks/tank-1/readings/aggregated`, () => {
        calls.aggregated += 1;
        return HttpResponse.json({});
      }),
    );
    const { hub, wrapper } = setup(["tank-1"]);
    render(<Probes />, { wrapper });
    await waitFor(() => expect(calls).toEqual({ list: 1, detail: 1, aggregated: 1 }));
    const socket = hub.latest("/tank-1");
    act(() => socket.open());

    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    act(() => socket.serverClose(1006));
    act(() => vi.advanceTimersByTime(1000));
    act(() => hub.latest("/tank-1").open());
    act(() => vi.advanceTimersByTime(LIST_INVALIDATION_DEBOUNCE_MS));
    vi.useRealTimers();
    await waitFor(() => expect(calls).toEqual({ list: 2, detail: 2, aggregated: 2 }));
  });
});

describe("useLiveReadings reconnect fan-out", () => {
  const listCalls = (spy: ReturnType<typeof vi.spyOn>) =>
    spy.mock.calls.filter(
      ([filters]: unknown[]) => JSON.stringify((filters as { queryKey: unknown[] }).queryKey) === JSON.stringify(tankKeys.list()),
    );
  const aggregatedOnly = (spy: ReturnType<typeof vi.spyOn>) =>
    spy.mock.calls.filter(([filters]: unknown[]) => (filters as { queryKey: unknown[] }).queryKey[0] === "readings");

  it("coalesces the list invalidation when many sockets reopen together", () => {
    vi.useFakeTimers();
    const { hub, queryClient } = setup(["a", "b", "c"]);
    const spy = vi.spyOn(queryClient, "invalidateQueries");
    const ids = ["/a", "/b", "/c"];
    ids.forEach((id) => act(() => hub.latest(id).open()));
    ids.forEach((id) => act(() => hub.latest(id).serverClose(1006)));
    act(() => vi.advanceTimersByTime(1000));
    ids.forEach((id) => act(() => hub.latest(id).open()));
    expect(listCalls(spy)).toHaveLength(0);
    act(() => vi.advanceTimersByTime(LIST_INVALIDATION_DEBOUNCE_MS));
    expect(listCalls(spy)).toHaveLength(1);
    expect(listCalls(spy)[0]?.[1]).toEqual({ cancelRefetch: false });
    act(() => vi.advanceTimersByTime(60_000));
    expect(listCalls(spy)).toHaveLength(1);
  });

  it("cancels a pending list invalidation on unmount", () => {
    vi.useFakeTimers();
    const { hub, queryClient, unmount } = setup(["a"]);
    const spy = vi.spyOn(queryClient, "invalidateQueries");
    act(() => hub.latest("/a").open());
    act(() => hub.latest("/a").serverClose(1006));
    act(() => vi.advanceTimersByTime(1000));
    act(() => hub.latest("/a").open());
    unmount();
    act(() => vi.advanceTimersByTime(60_000));
    expect(listCalls(spy)).toHaveLength(0);
  });

  it("routes the reconnect aggregated refetch through the per-tank throttle", () => {
    vi.useFakeTimers();
    const { hub, queryClient } = setup(["tank-1"]);
    const spy = vi.spyOn(queryClient, "invalidateQueries");
    const socket = hub.latest("/tank-1");
    act(() => socket.open());
    act(() => socket.message(wire("tank-1", 1, "2026-03-01T10:01:00Z")));
    expect(aggregatedOnly(spy)).toHaveLength(1);

    act(() => socket.serverClose(1006));
    act(() => vi.advanceTimersByTime(1000));
    act(() => hub.latest("/tank-1").open());
    expect(aggregatedOnly(spy)).toHaveLength(1);
    act(() => hub.latest("/tank-1").message(wire("tank-1", 2, "2026-03-01T10:02:00Z")));
    expect(aggregatedOnly(spy)).toHaveLength(1);

    act(() => vi.advanceTimersByTime(14_000));
    expect(aggregatedOnly(spy)).toHaveLength(2);
    act(() => vi.advanceTimersByTime(60_000));
    expect(aggregatedOnly(spy)).toHaveLength(2);
  });
});

describe("useLiveReadings aggregated throttling", () => {
  const aggregatedCalls = (spy: ReturnType<typeof vi.spyOn>) =>
    spy.mock.calls.filter(([filters]: unknown[]) => (filters as { queryKey: unknown[] }).queryKey[0] === "readings");

  it("invalidates aggregated queries at most once every 15 seconds per tank", () => {
    vi.useFakeTimers();
    const { hub, queryClient } = setup(["tank-1"]);
    const spy = vi.spyOn(queryClient, "invalidateQueries");
    const socket = hub.latest("/tank-1");
    act(() => socket.open());

    act(() => socket.message(wire("tank-1", 1, "2026-03-01T10:01:00Z")));
    expect(aggregatedCalls(spy)).toHaveLength(1);
    expect(aggregatedCalls(spy)[0]?.[0]).toMatchObject({ queryKey: ["readings", "aggregated", "tank-1"] });

    act(() => vi.advanceTimersByTime(5_000));
    act(() => socket.message(wire("tank-1", 2, "2026-03-01T10:02:00Z")));
    act(() => socket.message(wire("tank-1", 3, "2026-03-01T10:03:00Z")));
    expect(aggregatedCalls(spy)).toHaveLength(1);

    act(() => vi.advanceTimersByTime(9_999));
    expect(aggregatedCalls(spy)).toHaveLength(1);
    act(() => vi.advanceTimersByTime(1));
    expect(aggregatedCalls(spy)).toHaveLength(2);

    act(() => vi.advanceTimersByTime(60_000));
    expect(aggregatedCalls(spy)).toHaveLength(2);
    act(() => socket.message(wire("tank-1", 4, "2026-03-01T10:04:00Z")));
    expect(aggregatedCalls(spy)).toHaveLength(3);
  });

  it("cancels a pending trailing invalidation on unmount", () => {
    vi.useFakeTimers();
    const { hub, queryClient, unmount } = setup(["tank-1"]);
    const spy = vi.spyOn(queryClient, "invalidateQueries");
    const socket = hub.latest("/tank-1");
    act(() => socket.open());
    act(() => socket.message(wire("tank-1", 1, "2026-03-01T10:01:00Z")));
    act(() => socket.message(wire("tank-1", 2, "2026-03-01T10:02:00Z")));
    unmount();
    act(() => vi.advanceTimersByTime(60_000));
    expect(aggregatedCalls(spy)).toHaveLength(1);
  });
});

