import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { API_URL } from "../shared/api";
import { createFakeSocketHub } from "../test/fakeSocket";
import { makeAlert, makeBatch, makeTank } from "../test/fixtures";
import { renderWithProviders } from "../test/renderWithProviders";
import { server } from "../test/server";
import { AppRoutes } from "./AppRoutes";

// Empty series keep ECharts (no canvas in jsdom) out of the route tests.
function mockDetail(id: string) {
  server.use(
    http.get(`${API_URL}/tanks`, () => HttpResponse.json([makeTank(id)])),
    http.get(`${API_URL}/alerts`, () => HttpResponse.json([])),
    http.get(`${API_URL}/tanks/${id}`, () => HttpResponse.json(makeTank(id))),
    http.get(`${API_URL}/tanks/${id}/readings/aggregated`, () =>
      HttpResponse.json({ tank_id: id, bucket: "1h", series: { temperature: [], pressure: [], alcohol: [] } }),
    ),
  );
}

describe("AppRoutes", () => {
  it("renders the overview at /", async () => {
    server.use(http.get(`${API_URL}/tanks`, () => HttpResponse.json([makeTank("tank-1")])));
    renderWithProviders(<AppRoutes />, { route: "/" });
    expect(await screen.findByRole("heading", { level: 2, name: "Tanks" })).toBeInTheDocument();
  });

  it("renders the tank detail at /tanks/:tankId", async () => {
    mockDetail("tank-9");
    renderWithProviders(<AppRoutes />, { route: "/tanks/tank-9" });
    // First test to load the lazy detail page (with ECharts): under a full parallel run that import
    // can outlast the default 1 s wait, so allow more (still within Vitest's 5 s test timeout).
    expect(
      await screen.findByRole("heading", { level: 2, name: "tank-9" }, { timeout: 3000 }),
    ).toBeInTheDocument();
    expect(await screen.findAllByText("No data in this range")).toHaveLength(3);
  });

  it("shows not found for unknown routes, with a way back", async () => {
    renderWithProviders(<AppRoutes />, { route: "/nope" });
    expect(screen.getByRole("heading", { name: "Page not found" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to tanks" })).toHaveAttribute("href", "/");
  });

  it("navigates from a card to the tank detail", async () => {
    server.use(http.get(`${API_URL}/tanks`, () => HttpResponse.json([makeTank("tank-1")])));
    mockDetail("tank-1");
    renderWithProviders(<AppRoutes />, { route: "/" });
    await userEvent.click(await screen.findByRole("link", { name: "tank-1" }));
    expect(await screen.findByRole("radiogroup", { name: "Time range" })).toBeInTheDocument();
  });

  it("renders the batches list at /batches and links to the form", async () => {
    server.use(
      http.get(`${API_URL}/batches`, () => HttpResponse.json([])),
      http.get(`${API_URL}/tanks`, () => HttpResponse.json([makeTank("tank-1")])),
    );
    renderWithProviders(<AppRoutes />, { route: "/batches" });
    expect(await screen.findByRole("heading", { level: 2, name: "Batches" })).toBeInTheDocument();
    expect(await screen.findByText("No batches match these filters")).toBeInTheDocument();
  });

  it("renders the new batch form at /batches/new", async () => {
    server.use(
      http.get(`${API_URL}/batch-templates`, () => HttpResponse.json([])),
      http.get(`${API_URL}/tanks`, () => HttpResponse.json([makeTank("tank-1")])),
    );
    renderWithProviders(<AppRoutes />, { route: "/batches/new" });
    expect(await screen.findByRole("heading", { level: 2, name: "New batch" })).toBeInTheDocument();
    expect(await screen.findByLabelText("Beer name")).toBeInTheDocument();
  });

  it("renders a batch at /batches/:batchId", async () => {
    server.use(
      http.get(`${API_URL}/batches/b1`, () => HttpResponse.json(makeBatch())),
      http.get(`${API_URL}/batch-templates`, () => HttpResponse.json([])),
      http.get(`${API_URL}/tanks`, () => HttpResponse.json([makeTank("tank-1")])),
    );
    renderWithProviders(<AppRoutes />, { route: "/batches/b1" });
    expect(await screen.findByRole("heading", { level: 2, name: "Pale Ale" })).toBeInTheDocument();
  });

  it("navigates between sections with the header links", async () => {
    server.use(
      http.get(`${API_URL}/tanks`, () => HttpResponse.json([makeTank("tank-1")])),
      http.get(`${API_URL}/batches`, () => HttpResponse.json([])),
    );
    renderWithProviders(<AppRoutes />, { route: "/" });
    await userEvent.click(await screen.findByRole("link", { name: "Batches" }));
    expect(await screen.findByRole("heading", { level: 2, name: "Batches" })).toBeInTheDocument();
  });

  it("renders the alerts page at /alerts", async () => {
    server.use(
      http.get(`${API_URL}/tanks`, () => HttpResponse.json([makeTank("tank-1")])),
      http.get(`${API_URL}/alerts`, () => HttpResponse.json([makeAlert()])),
    );
    renderWithProviders(<AppRoutes />, { route: "/alerts" });
    expect(await screen.findByRole("heading", { level: 2, name: "Alerts" })).toBeInTheDocument();
    expect(await screen.findByText(/Temperature below target/)).toBeInTheDocument();
  });

  it("shows the unresolved total from the tanks in the nav, on every page", async () => {
    server.use(
      http.get(`${API_URL}/tanks`, () =>
        HttpResponse.json([makeTank("tank-1", { open_alerts: 2 }), makeTank("tank-2", { open_alerts: 1 })]),
      ),
    );
    renderWithProviders(<AppRoutes />, { route: "/" });
    expect(await screen.findByRole("link", { name: "Alerts 3 unresolved alerts" })).toHaveAttribute("href", "/alerts");
  });

  it("keeps one live alerts socket for the whole app and refreshes the counter on events", async () => {
    let open = 1;
    server.use(
      http.get(`${API_URL}/tanks`, () => HttpResponse.json([makeTank("tank-1", { open_alerts: open })])),
      http.get(`${API_URL}/alerts`, () => HttpResponse.json([])),
    );
    const hub = createFakeSocketHub();
    renderWithProviders(<AppRoutes />, { route: "/alerts", socketFactory: hub.factory });
    expect(await screen.findByRole("link", { name: "Alerts 1 unresolved alert" })).toBeInTheDocument();
    expect(hub.sockets.filter((s) => s.url.endsWith("/ws/alerts"))).toHaveLength(1);
    open = 2;
    act(() => hub.latest("/ws/alerts").message(JSON.stringify({ type: "alert", alert: makeAlert({ id: "a9" }) })));
    expect(await screen.findByRole("link", { name: "Alerts 2 unresolved alerts" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("link", { name: "Tanks" }));
    await screen.findByRole("heading", { level: 2, name: "Tanks" });
    expect(hub.sockets.filter((s) => s.url.endsWith("/ws/alerts"))).toHaveLength(1);
  });
});
