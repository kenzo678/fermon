import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { API_URL } from "../../shared/api";
import type { Alert } from "../../shared/api";
import { createFakeSocketHub } from "../../test/fakeSocket";
import { makeAlert, makeTank } from "../../test/fixtures";
import { renderWithProviders } from "../../test/renderWithProviders";
import { server } from "../../test/server";
import { AlertsPage } from "./AlertsPage";
import { LiveAlertsProvider } from "./LiveAlerts";

function mockAlerts(respond: (url: URL) => Alert[] | Response = () => []) {
  const urls: URL[] = [];
  server.use(
    http.get(`${API_URL}/tanks`, () => HttpResponse.json([makeTank("tank-1"), makeTank("tank-2")])),
    http.get(`${API_URL}/alerts`, ({ request }) => {
      const url = new URL(request.url);
      urls.push(url);
      const result = respond(url);
      return result instanceof Response ? result : HttpResponse.json(result);
    }),
  );
  return urls;
}

describe("AlertsPage", () => {
  it("lists unresolved alerts by default, as returned (newest first)", async () => {
    const urls = mockAlerts(() => [
      makeAlert({ id: "new", opened_at: "2026-03-01T13:00:00Z", details: { bound: "above", observed: 36, target_min: 30, target_max: 35 } }),
      makeAlert({ id: "old" }),
    ]);
    renderWithProviders(<AlertsPage />, { route: "/alerts" });
    const items = await screen.findAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("Temperature above target");
    expect(items[1]).toHaveTextContent("Temperature below target");
    expect(urls[0]?.searchParams.getAll("status")).toEqual(["open", "acknowledged"]);
    expect(screen.getByRole("checkbox", { name: "Open" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Acknowledged" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Resolved" })).not.toBeChecked();
  });

  it("reads the tank from the URL and sends it as tank_id", async () => {
    const urls = mockAlerts();
    renderWithProviders(<AlertsPage />, { route: "/alerts?tank=tank-2" });
    await screen.findByText("No alerts match these filters");
    expect(urls[0]?.searchParams.get("tank_id")).toBe("tank-2");
    await waitFor(() => expect(screen.getByLabelText("Tank")).toHaveValue("tank-2"));
  });

  it("adds resolved alerts to the request when that status is ticked", async () => {
    const urls = mockAlerts();
    renderWithProviders(<AlertsPage />, { route: "/alerts" });
    await screen.findByText("No alerts match these filters");
    await userEvent.click(screen.getByRole("checkbox", { name: "Resolved" }));
    await waitFor(() => expect(urls.at(-1)?.searchParams.getAll("status")).toEqual(["open", "acknowledged", "resolved"]));
  });

  it("never lets the last status be unticked", async () => {
    mockAlerts();
    renderWithProviders(<AlertsPage />, { route: "/alerts?status=open" });
    await screen.findByText("No alerts match these filters");
    await userEvent.click(screen.getByRole("checkbox", { name: "Open" }));
    expect(screen.getByRole("checkbox", { name: "Open" })).toBeChecked();
  });

  it("filters by kind and tank", async () => {
    const urls = mockAlerts();
    renderWithProviders(<AlertsPage />, { route: "/alerts" });
    await screen.findByRole("option", { name: "tank-2" });
    await userEvent.selectOptions(screen.getByLabelText("Kind"), "silent_sensor");
    await userEvent.selectOptions(screen.getByLabelText("Tank"), "tank-1");
    await waitFor(() => {
      const last = urls.at(-1);
      expect(last?.searchParams.get("kind")).toBe("silent_sensor");
      expect(last?.searchParams.get("tank_id")).toBe("tank-1");
    });
  });

  it("ignores invalid URL values", async () => {
    const urls = mockAlerts();
    renderWithProviders(<AlertsPage />, { route: "/alerts?status=bogus&kind=nope" });
    await screen.findByText("No alerts match these filters");
    expect(urls[0]?.searchParams.getAll("status")).toEqual(["open", "acknowledged"]);
    expect(urls[0]?.searchParams.has("kind")).toBe(false);
  });

  it("shows an error with retry", async () => {
    let calls = 0;
    mockAlerts(() => {
      calls += 1;
      return calls === 1 ? HttpResponse.json({ detail: [] }, { status: 500 }) : [makeAlert()];
    });
    renderWithProviders(<AlertsPage />, { route: "/alerts" });
    expect(await screen.findByRole("alert")).toHaveTextContent("Request failed with status 500");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText(/Temperature below target/)).toBeInTheDocument();
  });

  it("acknowledges an alert: pending and disabled while in flight, then acknowledged", async () => {
    let release!: () => void;
    const gate = new Promise<void>((resolve) => (release = resolve));
    let body: unknown;
    mockAlerts(() => [makeAlert()]);
    server.use(
      http.post(`${API_URL}/alerts/a1/acknowledge`, async ({ request }) => {
        body = await request.json();
        await gate;
        return HttpResponse.json(makeAlert({ status: "acknowledged", acknowledged_at: "2026-03-01T12:10:00Z", version: 2 }));
      }),
    );
    renderWithProviders(<AlertsPage />, { route: "/alerts" });
    await userEvent.click(await screen.findByRole("button", { name: "Acknowledge" }));
    expect(await screen.findByRole("button", { name: "Acknowledging…" })).toBeDisabled();
    release();
    const item = (await screen.findByText("Acknowledged", { selector: "span.rounded-full" })).closest("article")!;
    expect(within(item).queryByRole("button")).not.toBeInTheDocument();
    expect(body).toEqual({ version: 1 });
  });

  it("explains a conflict on an alert that was resolved meanwhile", async () => {
    mockAlerts(() => [makeAlert()]);
    server.use(
      http.post(`${API_URL}/alerts/a1/acknowledge`, () =>
        HttpResponse.json({ detail: [{ field: "status", message: "resolved" }] }, { status: 409 }),
      ),
    );
    renderWithProviders(<AlertsPage />, { route: "/alerts" });
    await userEvent.click(await screen.findByRole("button", { name: "Acknowledge" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("This alert was already resolved.");
  });

  it("shows live alerts and the connection state from the app-level socket", async () => {
    mockAlerts(() => []);
    const hub = createFakeSocketHub();
    renderWithProviders(
      <LiveAlertsProvider>
        <AlertsPage />
      </LiveAlertsProvider>,
      { route: "/alerts", socketFactory: hub.factory },
    );
    await screen.findByText("No alerts match these filters");
    expect(screen.getByRole("status", { name: "Connection: Reconnecting…" })).toBeInTheDocument();
    act(() => hub.latest("/ws/alerts").open());
    expect(screen.getByRole("status", { name: "Connection: Live" })).toBeInTheDocument();
    act(() => hub.latest("/ws/alerts").message(JSON.stringify({ type: "alert", alert: makeAlert() })));
    expect(await screen.findByText(/Temperature below target/)).toBeInTheDocument();
    expect(screen.queryByText("No alerts match these filters")).not.toBeInTheDocument();
  });
});
