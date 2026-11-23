import { QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { API_URL, ApiError } from "../../shared/api";
import type { Alert } from "../../shared/api";
import { makeAlert, makeTank } from "../../test/fixtures";
import { createTestQueryClient } from "../../test/renderWithProviders";
import { server } from "../../test/server";
import { tankKeys } from "../tanks/api";
import { useTanksQuery } from "../tanks/useTanksQuery";
import { alertKeys } from "./api";
import { acknowledgeErrorMessage, useAcknowledgeAlert, useAlertsQuery } from "./hooks";

function setup() {
  const queryClient = createTestQueryClient();
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return { queryClient, wrapper };
}

describe("alertKeys", () => {
  it("nests list keys under the lists prefix", () => {
    expect(alertKeys.list({ tank_id: "t" }).slice(0, 2)).toEqual(alertKeys.lists());
    expect(alertKeys.lists().slice(0, 1)).toEqual(alertKeys.all);
  });
});

describe("useAlertsQuery", () => {
  it("sends the filters as query params, with repeated status", async () => {
    let url: URL | undefined;
    server.use(
      http.get(`${API_URL}/alerts`, ({ request }) => {
        url = new URL(request.url);
        return HttpResponse.json([makeAlert()]);
      }),
    );
    const { wrapper } = setup();
    const { result } = renderHook(
      () =>
        useAlertsQuery({
          tank_id: "tank-1",
          batch_id: "b1",
          kind: "silent_sensor",
          status: ["open", "resolved"],
          limit: 50,
        }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(url?.searchParams.get("tank_id")).toBe("tank-1");
    expect(url?.searchParams.get("batch_id")).toBe("b1");
    expect(url?.searchParams.get("kind")).toBe("silent_sensor");
    expect(url?.searchParams.getAll("status")).toEqual(["open", "resolved"]);
    expect(url?.searchParams.get("limit")).toBe("50");
    expect(result.current.data).toEqual([makeAlert()]);
  });

  it("sends no params when there are no filters", async () => {
    let search = "?";
    server.use(
      http.get(`${API_URL}/alerts`, ({ request }) => {
        search = new URL(request.url).search;
        return HttpResponse.json([]);
      }),
    );
    const { wrapper } = setup();
    const { result } = renderHook(() => useAlertsQuery({}), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(search).toBe("");
  });
});

describe("useAcknowledgeAlert", () => {
  const acknowledged = (alert: Alert): Alert => ({
    ...alert,
    status: "acknowledged",
    acknowledged_at: "2026-03-01T12:10:00Z",
    version: alert.version + 1,
  });

  it("posts the current version, updates cached lists and refetches the tanks", async () => {
    let body: unknown;
    let tankRequests = 0;
    server.use(
      http.post(`${API_URL}/alerts/a1/acknowledge`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(acknowledged(makeAlert()));
      }),
      http.get(`${API_URL}/tanks`, () => {
        tankRequests += 1;
        return HttpResponse.json([makeTank("tank-1", { open_alerts: 1 })]);
      }),
    );
    const { queryClient, wrapper } = setup();
    const key = alertKeys.list({});
    queryClient.setQueryData<Alert[]>(key, [makeAlert()]);
    queryClient.setQueryData(tankKeys.list(), [makeTank("tank-1", { open_alerts: 1 })]);
    // Active observer: only active queries refetch on invalidation.
    renderHook(() => useTanksQuery(), { wrapper });
    await waitFor(() => expect(tankRequests).toBe(1));
    const { result } = renderHook(() => useAcknowledgeAlert(), { wrapper });

    act(() => result.current.mutate(makeAlert()));
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(body).toEqual({ version: 1 });
    expect(queryClient.getQueryData<Alert[]>(key)?.[0]).toMatchObject({ status: "acknowledged", version: 2 });
    await waitFor(() => expect(tankRequests).toBe(2));
  });

  it("surfaces a 409 on status and refetches the alert lists", async () => {
    let listRequests = 0;
    server.use(
      http.post(`${API_URL}/alerts/a1/acknowledge`, () =>
        HttpResponse.json({ detail: [{ field: "status", message: "resolved" }] }, { status: 409 }),
      ),
      http.get(`${API_URL}/alerts`, () => {
        listRequests += 1;
        return HttpResponse.json([]);
      }),
    );
    const { queryClient, wrapper } = setup();
    queryClient.setQueryData<Alert[]>(alertKeys.list({}), [makeAlert()]);
    // An observer keeps the list active so the invalidation refetches it.
    renderHook(() => useAlertsQuery({}), { wrapper });
    const { result } = renderHook(() => useAcknowledgeAlert(), { wrapper });

    act(() => result.current.mutate(makeAlert()));
    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(acknowledgeErrorMessage(result.current.error)).toBe("This alert was already resolved.");
    await waitFor(() => expect(listRequests).toBeGreaterThan(0));
  });

  it("explains a 409 on version as a stale alert", () => {
    const error = new ApiError(409, [{ field: "version", message: "stale" }]);
    expect(acknowledgeErrorMessage(error)).toBe("This alert changed in the meantime. It was refreshed; try again.");
  });

  it("falls back to the error message for anything else", () => {
    expect(acknowledgeErrorMessage(new ApiError(500, []))).toBe("Request failed with status 500");
    expect(acknowledgeErrorMessage(null)).toBeNull();
  });
});
