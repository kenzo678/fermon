import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { API_URL } from "../shared/api";
import { makeTank } from "../test/fixtures";
import { renderWithProviders } from "../test/renderWithProviders";
import { server } from "../test/server";
import { AppRoutes } from "./AppRoutes";

// Empty series keep ECharts (no canvas in jsdom) out of the route tests.
function mockDetail(id: string) {
  server.use(
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
    expect(await screen.findByRole("heading", { level: 2, name: "tank-9" })).toBeInTheDocument();
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
});
