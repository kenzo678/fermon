import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { Route, Routes, useLocation } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { API_URL } from "../../shared/api";
import type { AggregatedPoint, AggregatedReadings } from "../../shared/api";
import { createFakeSocketHub } from "../../test/fakeSocket";
import { makeTank } from "../../test/fixtures";
import { renderWithProviders } from "../../test/renderWithProviders";
import { server } from "../../test/server";

vi.mock("../readings/components/TimeSeriesChart", () => ({
  TimeSeriesChart: ({ label, option }: { label: string; option: { series: unknown[] } }) => (
    <div data-testid="chart" data-label={label} data-option={JSON.stringify(option)} />
  ),
}));

import { TankDetailPage } from "./TankDetailPage";

const tankUrl = `${API_URL}/tanks/tank-1`;
const aggUrl = `${API_URL}/tanks/tank-1/readings/aggregated`;

const point = (avg: number): AggregatedPoint => ({
  bucket_start: "2026-03-01T10:00:00Z",
  avg,
  min: avg - 1,
  max: avg + 1,
  count: 5,
});

function aggregated(series: AggregatedReadings["series"]): AggregatedReadings {
  return { tank_id: "tank-1", bucket: "1h", series };
}

const fullSeries = aggregated({
  temperature: [point(18)],
  pressure: [point(1.2)],
  alcohol: [point(4.5)],
});

function Page() {
  const location = useLocation();
  return (
    <>
      <Routes>
        <Route path="/tanks/:tankId" element={<TankDetailPage />} />
        <Route path="/" element={<p>overview</p>} />
      </Routes>
      <output data-testid="search">{location.search}</output>
    </>
  );
}

function useHappyPath(onAggregated?: (params: URLSearchParams) => void) {
  server.use(
    http.get(tankUrl, () => HttpResponse.json(makeTank("tank-1", { display_name: "Pale Ale" }))),
    http.get(aggUrl, ({ request }) => {
      onAggregated?.(new URL(request.url).searchParams);
      return HttpResponse.json(fullSeries);
    }),
  );
}

function averageOf(chart: HTMLElement | undefined): number | undefined {
  const option = JSON.parse(chart?.dataset.option ?? "{}") as {
    series: Array<{ name: string; data: [number, number][] }>;
  };
  return option.series.find((s) => s.name === "Average")?.data[0]?.[1];
}

describe("TankDetailPage", () => {
  it("shows the tank header and one chart per measurement with its series", async () => {
    useHappyPath();
    renderWithProviders(<Page />, { route: "/tanks/tank-1" });
    expect(await screen.findByRole("heading", { level: 2, name: "Pale Ale" })).toBeInTheDocument();
    expect(screen.getByText("tank-1")).toBeInTheDocument();
    expect(screen.getByText(/First seen/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to tanks" })).toHaveAttribute("href", "/");

    const charts = await screen.findAllByTestId("chart");
    expect(charts).toHaveLength(3);
    expect(charts.map((c) => c.dataset.label)).toEqual([
      "Temperature (°C) over time",
      "Pressure (bar) over time",
      "Alcohol (% ABV) over time",
    ]);
    expect(charts.map(averageOf)).toEqual([18, 1.2, 4.5]);
  });

  it("requests the default range with all measurements in one call", async () => {
    const calls: URLSearchParams[] = [];
    useHappyPath((p) => calls.push(p));
    renderWithProviders(<Page />, { route: "/tanks/tank-1" });
    await screen.findAllByTestId("chart");
    expect(calls).toHaveLength(1);
    expect(calls[0]?.get("bucket")).toBe("1h");
    expect(calls[0]?.getAll("measurement")).toEqual([]);
    const window = Date.parse(calls[0]?.get("end") ?? "") - Date.parse(calls[0]?.get("start") ?? "");
    expect(window).toBe(24 * 3_600_000);
    expect(screen.getByRole("radio", { name: "Last 24 hours" })).toBeChecked();
  });

  it("reads the range from the URL", async () => {
    const calls: URLSearchParams[] = [];
    useHappyPath((p) => calls.push(p));
    renderWithProviders(<Page />, { route: "/tanks/tank-1?range=1h" });
    await screen.findAllByTestId("chart");
    expect(calls[0]?.get("bucket")).toBe("1m");
    expect(screen.getByRole("radio", { name: "Last hour" })).toBeChecked();
  });

  it("falls back to the default range for an invalid URL value", async () => {
    useHappyPath();
    renderWithProviders(<Page />, { route: "/tanks/tank-1?range=bogus" });
    await screen.findAllByTestId("chart");
    expect(screen.getByRole("radio", { name: "Last 24 hours" })).toBeChecked();
  });

  it("refetches with new params and updates the URL when the range changes", async () => {
    const calls: URLSearchParams[] = [];
    useHappyPath((p) => calls.push(p));
    renderWithProviders(<Page />, { route: "/tanks/tank-1" });
    await screen.findAllByTestId("chart");
    await userEvent.click(screen.getByRole("radio", { name: "Last 6 hours" }));
    await waitFor(() => expect(calls).toHaveLength(2));
    expect(calls[1]?.get("bucket")).toBe("1m");
    const window = Date.parse(calls[1]?.get("end") ?? "") - Date.parse(calls[1]?.get("start") ?? "");
    expect(window).toBe(6 * 3_600_000);
    expect(screen.getByTestId("search")).toHaveTextContent("range=6h");
  });

  it("shows a not found state with a way back when the tank does not exist", async () => {
    server.use(
      http.get(tankUrl, () =>
        HttpResponse.json({ detail: [{ field: null, message: "Tank not found" }] }, { status: 404 }),
      ),
      http.get(aggUrl, () =>
        HttpResponse.json({ detail: [{ field: null, message: "Tank not found" }] }, { status: 404 }),
      ),
    );
    renderWithProviders(<Page />, { route: "/tanks/tank-1" });
    expect(await screen.findByRole("heading", { name: "Tank not found" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to tanks" })).toHaveAttribute("href", "/");
    expect(screen.queryByTestId("chart")).not.toBeInTheDocument();
  });

  it("shows an error with retry when the tank request fails", async () => {
    let calls = 0;
    server.use(
      http.get(tankUrl, () => {
        calls += 1;
        return calls === 1
          ? HttpResponse.json({ detail: [{ field: null, message: "Boom" }] }, { status: 500 })
          : HttpResponse.json(makeTank("tank-1"));
      }),
      http.get(aggUrl, () => HttpResponse.json(fullSeries)),
    );
    renderWithProviders(<Page />, { route: "/tanks/tank-1" });
    expect(await screen.findByRole("alert")).toHaveTextContent("Boom");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { level: 2, name: "tank-1" })).toBeInTheDocument();
  });

  it("keeps the header and shows an error with retry when the aggregated call fails", async () => {
    let calls = 0;
    server.use(
      http.get(tankUrl, () => HttpResponse.json(makeTank("tank-1"))),
      http.get(aggUrl, () => {
        calls += 1;
        return calls === 1
          ? HttpResponse.json({ detail: [{ field: null, message: "Down" }] }, { status: 503 })
          : HttpResponse.json(fullSeries);
      }),
    );
    renderWithProviders(<Page />, { route: "/tanks/tank-1" });
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Down");
    expect(screen.getByRole("heading", { level: 2, name: "tank-1" })).toBeInTheDocument();
    await userEvent.click(within(alert).getByRole("button", { name: "Try again" }));
    expect(await screen.findAllByTestId("chart")).toHaveLength(3);
  });

  it("shows the empty message for a measurement without data", async () => {
    server.use(
      http.get(tankUrl, () => HttpResponse.json(makeTank("tank-1"))),
      http.get(aggUrl, () =>
        HttpResponse.json(aggregated({ temperature: [point(18)], pressure: [], alcohol: [] })),
      ),
    );
    renderWithProviders(<Page />, { route: "/tanks/tank-1" });
    expect(await screen.findAllByTestId("chart")).toHaveLength(1);
    expect(screen.getAllByText("No data in this range")).toHaveLength(2);
  });

  it("shows the message of a 422 from the guard", async () => {
    server.use(
      http.get(tankUrl, () => HttpResponse.json(makeTank("tank-1"))),
      http.get(aggUrl, () =>
        HttpResponse.json(
          { detail: [{ field: null, message: "Too many points for bucket 1m (max 10000)" }] },
          { status: 422 },
        ),
      ),
    );
    renderWithProviders(<Page />, { route: "/tanks/tank-1" });
    expect(await screen.findByRole("alert")).toHaveTextContent("Too many points for bucket 1m");
  });

  it("shows the connection indicator and survives a terminal socket close", async () => {
    useHappyPath();
    const hub = createFakeSocketHub();
    renderWithProviders(<Page />, { route: "/tanks/tank-1", socketFactory: hub.factory });
    await screen.findAllByTestId("chart");
    const socket = hub.latest("/ws/tanks/tank-1");
    act(() => socket.open());
    expect(screen.getByRole("status", { name: "Connection: Live" })).toBeInTheDocument();
    act(() => socket.serverClose(4404));
    expect(screen.getByRole("status", { name: "Connection: Offline" })).toBeInTheDocument();
    expect(screen.getAllByTestId("chart")).toHaveLength(3);
  });
});
