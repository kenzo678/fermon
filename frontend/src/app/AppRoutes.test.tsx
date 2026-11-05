import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { API_URL } from "../shared/api";
import { makeTank } from "../test/fixtures";
import { renderWithProviders } from "../test/renderWithProviders";
import { server } from "../test/server";
import { AppRoutes } from "./AppRoutes";

describe("AppRoutes", () => {
  it("renders the overview at /", async () => {
    server.use(http.get(`${API_URL}/tanks`, () => HttpResponse.json([makeTank("tank-1")])));
    renderWithProviders(<AppRoutes />, { route: "/" });
    expect(await screen.findByRole("heading", { level: 2, name: "Tanks" })).toBeInTheDocument();
  });

  it("shows the detail placeholder at /tanks/:tankId", () => {
    renderWithProviders(<AppRoutes />, { route: "/tanks/tank-9" });
    expect(screen.getByRole("heading", { name: "Tank detail — coming soon" })).toBeInTheDocument();
    expect(screen.getByText("tank-9")).toBeInTheDocument();
  });

  it("shows not found for unknown routes, with a way back", async () => {
    renderWithProviders(<AppRoutes />, { route: "/nope" });
    expect(screen.getByRole("heading", { name: "Page not found" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to tanks" })).toHaveAttribute("href", "/");
  });

  it("navigates from a card to the detail placeholder", async () => {
    server.use(http.get(`${API_URL}/tanks`, () => HttpResponse.json([makeTank("tank-1")])));
    renderWithProviders(<AppRoutes />, { route: "/" });
    await userEvent.click(await screen.findByRole("link", { name: "tank-1" }));
    expect(screen.getByRole("heading", { name: "Tank detail — coming soon" })).toBeInTheDocument();
  });
});
