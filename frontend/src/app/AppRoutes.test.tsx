import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { API_URL } from "../shared/api";
import { createFakeSocketHub } from "../test/fakeSocket";
import { makeAlert, makeBatch, makeQualityProfile, makeTank, makeUser } from "../test/fixtures";
import { renderWithProviders } from "../test/renderWithProviders";
import { server } from "../test/server";
import { AppRoutes } from "./AppRoutes";
import { createQueryClient } from "./queryClient";

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

  it("renders the quality profiles list at /quality-profiles, with its nav item for a viewer", async () => {
    server.use(
      http.get(`${API_URL}/quality-profiles`, () => HttpResponse.json([makeQualityProfile()])),
      http.get(`${API_URL}/quality-profile-templates`, () => HttpResponse.json([])),
      http.get(`${API_URL}/alerts`, () => HttpResponse.json([])),
    );
    renderWithProviders(<AppRoutes />, { route: "/quality-profiles", user: makeUser({ role: "viewer" }) });
    expect(await screen.findByRole("heading", { level: 2, name: "Quality profiles" })).toBeInTheDocument();
    expect(await screen.findAllByRole("link", { name: "House lager" })).not.toHaveLength(0);
    expect(screen.getByRole("link", { name: "Quality" })).toHaveAttribute("aria-current", "page");
    expect(screen.queryByRole("button", { name: "New profile" })).not.toBeInTheDocument();
  });

  it("renders a quality profile at /quality-profiles/:profileId", async () => {
    server.use(
      http.get(`${API_URL}/quality-profiles/p1`, () => HttpResponse.json(makeQualityProfile())),
      http.get(`${API_URL}/quality-parameters`, () => HttpResponse.json([])),
      http.get(`${API_URL}/alerts`, () => HttpResponse.json([])),
    );
    renderWithProviders(<AppRoutes />, { route: "/quality-profiles/p1" });
    expect(await screen.findByRole("heading", { level: 2, name: "House lager" })).toBeInTheDocument();
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

describe("AppRoutes authentication", () => {
  it("sends an anonymous visitor to the login page and opens no sockets", () => {
    const hub = createFakeSocketHub();
    renderWithProviders(<AppRoutes />, { route: "/batches", user: null, socketFactory: hub.factory });
    expect(screen.getByRole("heading", { level: 2, name: "Sign in" })).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Main" })).not.toBeInTheDocument();
    expect(hub.sockets).toHaveLength(0);
  });

  it("returns to the requested page after signing in", async () => {
    server.use(
      http.post(`${API_URL}/auth/login`, () => HttpResponse.json({ user: makeUser() })),
      http.get(`${API_URL}/batches`, () => HttpResponse.json([])),
      http.get(`${API_URL}/tanks`, () => HttpResponse.json([makeTank("tank-1")])),
    );
    const user = userEvent.setup();
    renderWithProviders(<AppRoutes />, { route: "/batches", user: null });
    await user.type(screen.getByLabelText("Email"), "ada@example.com");
    await user.type(screen.getByLabelText("Password"), "correct horse");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("heading", { level: 2, name: "Batches" })).toBeInTheDocument();
  });

  it("shows who is signed in and signs out back to the login page", async () => {
    server.use(
      http.get(`${API_URL}/tanks`, () => HttpResponse.json([makeTank("tank-1")])),
      http.post(`${API_URL}/auth/logout`, () => new HttpResponse(null, { status: 204 })),
    );
    renderWithProviders(<AppRoutes />, { route: "/", user: makeUser({ display_name: "Bea Brewer", role: "brewer" }) });
    const account = await screen.findByRole("group", { name: "Account" });
    expect(account).toHaveTextContent("Bea Brewer");
    expect(account).toHaveTextContent("brewer");
    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(await screen.findByRole("heading", { level: 2, name: "Sign in" })).toBeInTheDocument();
  });

  it("offers the Users section to admins only", async () => {
    server.use(http.get(`${API_URL}/tanks`, () => HttpResponse.json([makeTank("tank-1")])));
    const admin = renderWithProviders(<AppRoutes />, { route: "/", user: makeUser({ role: "admin" }) });
    expect(await screen.findByRole("link", { name: "Users" })).toHaveAttribute("href", "/users");
    admin.unmount();
    renderWithProviders(<AppRoutes />, { route: "/", user: makeUser({ role: "brewer" }) });
    await screen.findByRole("heading", { level: 2, name: "Tanks" });
    expect(screen.queryByRole("link", { name: "Users" })).not.toBeInTheDocument();
  });

  it("renders the users page for an admin and refuses everyone else", async () => {
    server.use(
      http.get(`${API_URL}/users`, () => HttpResponse.json([makeUser()])),
      http.get(`${API_URL}/tanks`, () => HttpResponse.json([])),
    );
    const admin = renderWithProviders(<AppRoutes />, { route: "/users", user: makeUser({ role: "admin" }) });
    expect(await screen.findByRole("heading", { level: 2, name: "Users" })).toBeInTheDocument();
    admin.unmount();
    renderWithProviders(<AppRoutes />, { route: "/users", user: makeUser({ role: "brewer" }) });
    expect(await screen.findByRole("heading", { name: "Not allowed" })).toBeInTheDocument();
  });

  it("keeps a viewer out of the new-batch form", async () => {
    server.use(http.get(`${API_URL}/tanks`, () => HttpResponse.json([])));
    renderWithProviders(<AppRoutes />, { route: "/batches/new", user: makeUser({ role: "viewer" }) });
    expect(await screen.findByRole("heading", { name: "Not allowed" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Beer name")).not.toBeInTheDocument();
  });

  it("confines a temporary password to the change-password page, with no navigation or sockets", () => {
    const hub = createFakeSocketHub();
    renderWithProviders(<AppRoutes />, {
      route: "/batches",
      user: makeUser({ must_change_password: true }),
      socketFactory: hub.factory,
    });
    expect(screen.getByRole("heading", { level: 2, name: "Change password" })).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Main" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign out" })).toBeInTheDocument();
    expect(hub.sockets).toHaveLength(0);
  });

  it("reaches the change-password page from the account menu", async () => {
    server.use(http.get(`${API_URL}/tanks`, () => HttpResponse.json([makeTank("tank-1")])));
    renderWithProviders(<AppRoutes />, { route: "/" });
    await userEvent.click(await screen.findByRole("link", { name: "Change password" }));
    expect(await screen.findByRole("heading", { level: 2, name: "Change password" })).toBeInTheDocument();
  });

  it("sends the user to login when the session ends under them", async () => {
    server.use(
      http.get(`${API_URL}/tanks`, () => HttpResponse.json({ detail: [] }, { status: 401 })),
      http.get(`${API_URL}/auth/me`, () => HttpResponse.json({ detail: [] }, { status: 401 })),
    );
    renderWithProviders(<AppRoutes />, { route: "/", queryClient: createQueryClient({ retry: false }) });
    expect(await screen.findByRole("heading", { level: 2, name: "Sign in" })).toBeInTheDocument();
  });
});
