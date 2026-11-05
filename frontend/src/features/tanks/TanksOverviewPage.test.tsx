import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { createQueryClient } from "../../app/queryClient";
import { API_URL } from "../../shared/api";
import { createFakeSocketHub } from "../../test/fakeSocket";
import { makeReading, makeTank } from "../../test/fixtures";
import { renderWithProviders } from "../../test/renderWithProviders";
import { server } from "../../test/server";
import { TanksOverviewPage } from "./TanksOverviewPage";

const url = `${API_URL}/tanks`;

describe("TanksOverviewPage", () => {
  it("shows a loading state, then a card per tank", async () => {
    server.use(http.get(url, () => HttpResponse.json([makeTank("tank-1"), makeTank("tank-2")])));
    renderWithProviders(<TanksOverviewPage />);
    expect(screen.getByRole("status", { name: "Loading tanks" })).toBeInTheDocument();
    const list = await screen.findByRole("list", { name: "Tanks" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByRole("heading", { level: 2, name: "Tanks" })).toBeInTheDocument();
    expect(screen.queryByRole("status", { name: "Loading tanks" })).not.toBeInTheDocument();
  });

  it("shows the empty state for an empty list", async () => {
    server.use(http.get(url, () => HttpResponse.json([])));
    renderWithProviders(<TanksOverviewPage />);
    expect(await screen.findByRole("heading", { name: "No tanks yet" })).toBeInTheDocument();
  });

  it("shows the error state on a 500 and refetches on retry", async () => {
    let calls = 0;
    server.use(
      http.get(url, () => {
        calls += 1;
        return calls === 1
          ? HttpResponse.json({ detail: [{ field: null, message: "Boom" }] }, { status: 500 })
          : HttpResponse.json([makeTank("tank-1")]);
      }),
    );
    renderWithProviders(<TanksOverviewPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Boom");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("link", { name: "tank-1" })).toBeInTheDocument();
    expect(calls).toBe(2);
  });

  it("shows the error state on a network failure", async () => {
    server.use(http.get(url, () => HttpResponse.error()));
    renderWithProviders(<TanksOverviewPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/could not reach the API/i);
  });

  it("does not retry a 4xx response", async () => {
    let calls = 0;
    server.use(
      http.get(url, () => {
        calls += 1;
        return HttpResponse.json({ detail: [] }, { status: 404 });
      }),
    );
    renderWithProviders(<TanksOverviewPage />, {
      queryClient: createQueryClient({ retryDelay: 0 }),
    });
    await screen.findByRole("alert");
    await new Promise((resolve) => setTimeout(resolve, 100));
    expect(calls).toBe(1);
  });

  it("retries a server error before giving up", async () => {
    let calls = 0;
    server.use(
      http.get(url, () => {
        calls += 1;
        return new HttpResponse("oops", { status: 500 });
      }),
    );
    renderWithProviders(<TanksOverviewPage />, {
      queryClient: createQueryClient({ retryDelay: 0 }),
    });
    await screen.findByRole("alert");
    await waitFor(() => expect(calls).toBe(3));
  });

  it("keeps showing loaded tanks when a background refetch fails", async () => {
    server.use(http.get(url, () => HttpResponse.json([makeTank("tank-1")])));
    const { queryClient } = renderWithProviders(<TanksOverviewPage />);
    expect(await screen.findByRole("link", { name: "tank-1" })).toBeInTheDocument();

    server.use(
      http.get(url, () =>
        HttpResponse.json({ detail: [{ field: null, message: "Boom" }] }, { status: 500 }),
      ),
    );
    await act(() => queryClient.refetchQueries());

    expect(screen.getByRole("link", { name: "tank-1" })).toBeInTheDocument();
    expect(await screen.findByRole("status", { name: "Refresh failed" })).toBeInTheDocument();
  });

  // Characterization: TanStack Query v5 returns a data-less errored query to "pending" on
  // refetch, so the loading state replaces the retry button and it can't be clicked twice.
  it("replaces the retry button with the loading state while a retry is in flight", async () => {
    server.use(
      http.get(url, () =>
        HttpResponse.json({ detail: [{ field: null, message: "Boom" }] }, { status: 500 }),
      ),
    );
    renderWithProviders(<TanksOverviewPage />);
    const button = await screen.findByRole("button", { name: "Try again" });

    server.use(
      http.get(url, async () => {
        await delay(100);
        return HttpResponse.json([makeTank("tank-1")]);
      }),
    );
    await userEvent.click(button);

    expect(screen.getByRole("status", { name: "Loading tanks" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "tank-1" })).toBeInTheDocument();
  });
  describe("live updates", () => {
    it("shows the connection indicator and updates a card when a reading is pushed", async () => {
      server.use(http.get(url, () => HttpResponse.json([makeTank("tank-1")])));
      const hub = createFakeSocketHub();
      renderWithProviders(<TanksOverviewPage />, { socketFactory: hub.factory });
      await screen.findByRole("link", { name: "tank-1" });
      expect(screen.getByRole("status", { name: "Connection: Reconnecting…" })).toBeInTheDocument();

      const socket = hub.latest("/ws/tanks/tank-1");
      act(() => socket.open());
      expect(screen.getByRole("status", { name: "Connection: Live" })).toBeInTheDocument();
      expect(screen.getByText("18.5 °C")).toBeInTheDocument();

      act(() =>
        socket.message(
          JSON.stringify(makeReading("tank-1", "temperature", 21.3, "2026-03-01T10:05:00Z")),
        ),
      );
      // TanStack Query notifies observers asynchronously.
      expect(await screen.findByText("21.3 °C")).toBeInTheDocument();
      expect(screen.queryByText("18.5 °C")).not.toBeInTheDocument();
    });
  });
});
