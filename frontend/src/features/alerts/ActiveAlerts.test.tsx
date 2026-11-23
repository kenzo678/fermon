import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { API_URL } from "../../shared/api";
import { makeAlert } from "../../test/fixtures";
import { renderWithProviders } from "../../test/renderWithProviders";
import { server } from "../../test/server";
import { ActiveAlerts } from "./ActiveAlerts";

describe("ActiveAlerts", () => {
  it("lists the unresolved alerts of the tank and lets you acknowledge one", async () => {
    let url: URL | undefined;
    server.use(
      http.get(`${API_URL}/alerts`, ({ request }) => {
        url = new URL(request.url);
        return HttpResponse.json([makeAlert()]);
      }),
      http.post(`${API_URL}/alerts/a1/acknowledge`, () =>
        HttpResponse.json(makeAlert({ status: "acknowledged", version: 2 })),
      ),
    );
    renderWithProviders(<ActiveAlerts tankId="tank-1" />);
    expect(screen.getByRole("heading", { name: "Active alerts" })).toBeInTheDocument();
    await userEvent.click(await screen.findByRole("button", { name: "Acknowledge" }));
    expect(await screen.findByText("Acknowledged")).toBeInTheDocument();
    expect(url?.searchParams.get("tank_id")).toBe("tank-1");
    expect(url?.searchParams.has("status")).toBe(false);
    // The tank is the context, so the item does not repeat it.
    expect(screen.queryByRole("link", { name: "tank-1" })).not.toBeInTheDocument();
  });

  it("says so when there are none", async () => {
    server.use(http.get(`${API_URL}/alerts`, () => HttpResponse.json([])));
    renderWithProviders(<ActiveAlerts tankId="tank-1" />);
    expect(await screen.findByText("No active alerts")).toBeInTheDocument();
  });

  it("shows an error with retry", async () => {
    server.use(http.get(`${API_URL}/alerts`, () => HttpResponse.json({ detail: [] }, { status: 500 })));
    renderWithProviders(<ActiveAlerts tankId="tank-1" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Request failed with status 500");
  });
});
