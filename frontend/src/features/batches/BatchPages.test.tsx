import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";
import { Route, Routes } from "react-router";
import { describe, expect, it } from "vitest";
import { API_URL } from "../../shared/api";
import type { Batch, BatchTemplate } from "../../shared/api";
import { QUALITY_CATALOG, makeBatch, makeQualityProfile, makeTank, makeUser } from "../../test/fixtures";
import { createTestQueryClient, renderWithProviders } from "../../test/renderWithProviders";
import { server } from "../../test/server";
import { tankKeys } from "../tanks/api";
import { batchKeys } from "./api";
import { BatchDetailPage } from "./BatchDetailPage";
import { BatchesPage } from "./BatchesPage";
import { NewBatchPage } from "./NewBatchPage";

const templates: BatchTemplate[] = [
  {
    template: "ale",
    targets: { temperature_min: 18, temperature_max: 21, pressure_max: 1, pressure_min: null, expected_final_abv: 5 },
  },
  {
    template: "lager",
    targets: { temperature_min: 8, temperature_max: 12, pressure_max: 1.2, pressure_min: null, expected_final_abv: 5 },
  },
];

function mockCatalog() {
  server.use(
    http.get(`${API_URL}/tanks`, () => HttpResponse.json([makeTank("tank-1"), makeTank("tank-2")])),
    http.get(`${API_URL}/batch-templates`, () => HttpResponse.json(templates)),
    http.get(`${API_URL}/quality-profiles`, () => HttpResponse.json(profiles)),
    http.get(`${API_URL}/quality-parameters`, () => HttpResponse.json(QUALITY_CATALOG)),
    http.get(`${API_URL}/batches/:batchId/lab-analyses`, () => HttpResponse.json([])),
  );
}

const profiles = [
  makeQualityProfile({ id: "p1", name: "House lager" }),
  makeQualityProfile({ id: "p2", name: "Seasonal" }),
];

function Pages() {
  return (
    <Routes>
      <Route path="/batches" element={<BatchesPage />} />
      <Route path="/batches/new" element={<NewBatchPage />} />
      <Route path="/batches/:batchId" element={<BatchDetailPage />} />
    </Routes>
  );
}

describe("NewBatchPage", () => {
  async function fill(user: ReturnType<typeof userEvent.setup>) {
    await screen.findByRole("option", { name: "tank-2" });
    await user.selectOptions(screen.getByLabelText("Tank"), "tank-2");
    await user.type(screen.getByLabelText("Beer name"), "Pale Ale");
    await user.type(screen.getByLabelText("Style"), "APA");
    await user.selectOptions(screen.getByLabelText("Template"), "ale");
  }

  it("creates the batch from a template and navigates to it", async () => {
    mockCatalog();
    let body: unknown;
    server.use(
      http.post(`${API_URL}/batches`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(makeBatch({ id: "new-1" }), { status: 201 });
      }),
      http.get(`${API_URL}/batches/new-1`, () => HttpResponse.json(makeBatch({ id: "new-1" }))),
    );
    const user = userEvent.setup();
    renderWithProviders(<Pages />, { route: "/batches/new" });
    await fill(user);
    await user.click(screen.getByRole("button", { name: "Create batch" }));
    expect(await screen.findByRole("heading", { level: 2, name: "Pale Ale" })).toBeInTheDocument();
    expect(body).toMatchObject({
      tank_id: "tank-2",
      beer_name: "Pale Ale",
      style: "APA",
      template: "ale",
      targets: { temperature_min: 18, temperature_max: 21, pressure_max: 1, expected_final_abv: 5 },
    });
    expect((body as { planned_start: string }).planned_start).toMatch(/Z$/);
  });

  it("preselects the tank from the query string", async () => {
    mockCatalog();
    renderWithProviders(<Pages />, { route: "/batches/new?tank=tank-2" });
    await screen.findByRole("option", { name: "tank-2" });
    expect(screen.getByLabelText("Tank")).toHaveValue("tank-2");
  });

  it("maps a server 422 on a target field next to its input", async () => {
    mockCatalog();
    server.use(
      http.post(`${API_URL}/batches`, () =>
        HttpResponse.json(
          { detail: [{ field: "targets.temperature_max", message: "Temperature out of range" }] },
          { status: 422 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(<Pages />, { route: "/batches/new" });
    await fill(user);
    await user.click(screen.getByRole("button", { name: "Create batch" }));
    expect(await screen.findByLabelText("Maximum temperature (°C)")).toHaveAccessibleDescription(
      "Temperature out of range",
    );
  });

  it("explains that the tank already has an active batch", async () => {
    mockCatalog();
    server.use(
      http.post(`${API_URL}/batches`, () =>
        HttpResponse.json({ detail: [{ field: "tank_id", message: "active" }] }, { status: 409 }),
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(<Pages />, { route: "/batches/new" });
    await fill(user);
    await user.click(screen.getByRole("button", { name: "Create batch" }));
    await waitFor(() =>
      expect(screen.getByLabelText("Tank")).toHaveAccessibleDescription(
        "Another batch is already active in this tank.",
      ),
    );
  });

  it("offers the quality profiles with None by default and sends the chosen one", async () => {
    mockCatalog();
    let body: unknown;
    server.use(
      http.post(`${API_URL}/batches`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(makeBatch({ id: "new-1", quality_profile_id: "p2" }), { status: 201 });
      }),
      http.get(`${API_URL}/batches/new-1`, () => HttpResponse.json(makeBatch({ id: "new-1" }))),
    );
    const user = userEvent.setup();
    renderWithProviders(<Pages />, { route: "/batches/new" });
    await fill(user);
    const select = screen.getByLabelText("Quality profile");
    expect(select).toHaveValue("");
    expect(within(select).getByRole("option", { name: "None" })).toBeInTheDocument();
    await user.selectOptions(select, "Seasonal");
    await user.click(screen.getByRole("button", { name: "Create batch" }));
    await screen.findByRole("heading", { level: 2, name: "Pale Ale" });
    expect(body).toMatchObject({ quality_profile_id: "p2" });
  });

  it("omits the profile when None is kept", async () => {
    mockCatalog();
    let body: unknown;
    server.use(
      http.post(`${API_URL}/batches`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(makeBatch({ id: "new-1" }), { status: 201 });
      }),
      http.get(`${API_URL}/batches/new-1`, () => HttpResponse.json(makeBatch({ id: "new-1" }))),
    );
    const user = userEvent.setup();
    renderWithProviders(<Pages />, { route: "/batches/new" });
    await fill(user);
    await user.click(screen.getByRole("button", { name: "Create batch" }));
    await screen.findByRole("heading", { level: 2, name: "Pale Ale" });
    expect(body).not.toHaveProperty("quality_profile_id");
  });

  it("maps a 404 on the profile next to its select", async () => {
    mockCatalog();
    server.use(
      http.post(`${API_URL}/batches`, () =>
        HttpResponse.json(
          { detail: [{ field: "quality_profile_id", message: "Quality profile not found" }] },
          { status: 404 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(<Pages />, { route: "/batches/new" });
    await fill(user);
    await user.selectOptions(screen.getByLabelText("Quality profile"), "House lager");
    await user.click(screen.getByRole("button", { name: "Create batch" }));
    await waitFor(() =>
      expect(screen.getByLabelText("Quality profile")).toHaveAccessibleDescription("Quality profile not found"),
    );
  });

  it("shows an error state when tanks fail to load", async () => {
    server.use(
      http.get(`${API_URL}/tanks`, () => HttpResponse.json({ detail: [] }, { status: 500 })),
      http.get(`${API_URL}/batch-templates`, () => HttpResponse.json(templates)),
      http.get(`${API_URL}/quality-profiles`, () => HttpResponse.json(profiles)),
    );
    renderWithProviders(<Pages />, { route: "/batches/new" });
    expect(await screen.findByRole("alert")).toHaveTextContent("Request failed with status 500");
  });

  it("retries both the tanks and the templates from the error state", async () => {
    const calls = { tanks: 0, templates: 0 };
    server.use(
      http.get(`${API_URL}/tanks`, () => {
        calls.tanks += 1;
        return calls.tanks === 1
          ? HttpResponse.json({ detail: [] }, { status: 500 })
          : HttpResponse.json([makeTank("tank-1"), makeTank("tank-2")]);
      }),
      http.get(`${API_URL}/batch-templates`, () => {
        calls.templates += 1;
        return calls.templates === 1
          ? HttpResponse.json({ detail: [] }, { status: 500 })
          : HttpResponse.json(templates);
      }),
      http.get(`${API_URL}/quality-profiles`, () => HttpResponse.json(profiles)),
    );
    const user = userEvent.setup();
    renderWithProviders(<Pages />, { route: "/batches/new" });
    await user.click(await screen.findByRole("button", { name: "Try again" }));
    expect(await screen.findByLabelText("Beer name")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(calls).toEqual({ tanks: 2, templates: 2 });
  });
});

describe("BatchDetailPage", () => {
  function mockBatch(initial: Batch) {
    let current = initial;
    mockCatalog();
    server.use(
      http.get(`${API_URL}/batches/${initial.id}`, () => HttpResponse.json(current)),
      http.post(`${API_URL}/batches/${initial.id}/start`, () => {
        current = { ...current, status: "active", started_at: "2026-03-01T10:05:00Z", version: current.version + 1 };
        return HttpResponse.json(current);
      }),
      http.post(`${API_URL}/batches/${initial.id}/finish`, () => {
        current = { ...current, status: "finished", finished_at: "2026-03-05T10:00:00Z", version: current.version + 1 };
        return HttpResponse.json(current);
      }),
    );
  }

  it("shows a planned batch with an editable form and a Start button", async () => {
    mockBatch(makeBatch());
    renderWithProviders(<Pages />, { route: "/batches/b1" });
    expect(await screen.findByRole("heading", { level: 2, name: "Pale Ale" })).toBeInTheDocument();
    expect(screen.getByText("Planned")).toBeInTheDocument();
    expect(screen.getByLabelText("Beer name")).toHaveValue("Pale Ale");
    expect(screen.getByRole("button", { name: "Start batch" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "tank-1" })).toHaveAttribute("href", "/tanks/tank-1");
  });

  it("starts the batch, updates the UI and refetches the tanks", async () => {
    mockBatch(makeBatch());
    let tankRequests = 0;
    server.use(
      http.get(`${API_URL}/tanks`, () => {
        tankRequests += 1;
        return HttpResponse.json([makeTank("tank-1")]);
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<Pages />, { route: "/batches/b1" });
    await user.click(await screen.findByRole("button", { name: "Start batch" }));
    expect(await screen.findByText("Active")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Finish batch" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Start batch" })).not.toBeInTheDocument();
    // The page mounts one tank query; the mutation must invalidate it so cards show the new batch.
    await waitFor(() => expect(tankRequests).toBe(2));
  });

  it("invalidates cached batch lists and tanks after a change", async () => {
    mockBatch(makeBatch());
    const queryClient = createTestQueryClient();
    queryClient.setQueryData(tankKeys.detail("tank-1"), makeTank("tank-1"));
    queryClient.setQueryData(batchKeys.list({}), [makeBatch()]);
    const user = userEvent.setup();
    renderWithProviders(<Pages />, { route: "/batches/b1", queryClient });
    await user.click(await screen.findByRole("button", { name: "Start batch" }));
    await screen.findByText("Active");
    expect(queryClient.getQueryState(tankKeys.detail("tank-1"))?.isInvalidated).toBe(true);
    expect(queryClient.getQueryState(batchKeys.list({}))?.isInvalidated).toBe(true);
  });

  it("explains a start conflict when the tank already has an active batch", async () => {
    mockBatch(makeBatch());
    server.use(
      http.post(`${API_URL}/batches/b1/start`, () =>
        HttpResponse.json({ detail: [{ field: "tank_id", message: "active" }] }, { status: 409 }),
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(<Pages />, { route: "/batches/b1" });
    await user.click(await screen.findByRole("button", { name: "Start batch" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Another batch is already active in this tank.");
  });

  it("asks for confirmation before finishing and then makes the batch read-only", async () => {
    mockBatch(makeBatch({ status: "active", started_at: "2026-03-01T10:05:00Z", version: 2 }));
    const user = userEvent.setup();
    renderWithProviders(<Pages />, { route: "/batches/b1" });
    await user.click(await screen.findByRole("button", { name: "Finish batch" }));
    expect(screen.getByText(/can't be undone/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByText(/can't be undone/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Finish batch" }));
    await user.click(screen.getByRole("button", { name: "Yes, finish batch" }));
    expect(await screen.findByText("Finished")).toBeInTheDocument();
    expect(screen.getByLabelText("Beer name")).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Save changes" })).not.toBeInTheDocument();
  });

  it("shows the batch's profile in the form and saves a change or a clear", async () => {
    mockBatch(makeBatch({ version: 4, quality_profile_id: "p1" }));
    const bodies: Record<string, unknown>[] = [];
    server.use(
      http.patch(`${API_URL}/batches/b1`, async ({ request }) => {
        const body = (await request.json()) as Record<string, unknown>;
        bodies.push(body);
        return HttpResponse.json(makeBatch({ quality_profile_id: body.quality_profile_id as string | null, version: 5 }));
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<Pages />, { route: "/batches/b1" });
    await screen.findByRole("option", { name: "Seasonal" });
    expect(screen.getByLabelText("Quality profile")).toHaveValue("p1");
    await user.selectOptions(screen.getByLabelText("Quality profile"), "Seasonal");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(bodies[0]).toMatchObject({ quality_profile_id: "p2", version: 4 });
    await user.selectOptions(screen.getByLabelText("Quality profile"), "None");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(bodies).toHaveLength(2));
    expect(bodies[1]).toMatchObject({ quality_profile_id: null });
  });

  it("disables the profile select once the batch is finished", async () => {
    mockBatch(makeBatch({ status: "finished", quality_profile_id: "p1", version: 3 }));
    renderWithProviders(<Pages />, { route: "/batches/b1" });
    await screen.findByRole("option", { name: "Seasonal" });
    expect(screen.getByLabelText("Quality profile")).toBeDisabled();
  });

  it("shows the lab analyses of an active batch, and only a note while it is planned", async () => {
    mockBatch(makeBatch({ status: "active", started_at: "2026-03-01T10:05:00Z", version: 2 }));
    const { unmount } = renderWithProviders(<Pages />, { route: "/batches/b1" });
    expect(await screen.findByRole("heading", { name: "Lab analyses" })).toBeInTheDocument();
    expect(await screen.findByText("No analyses recorded yet")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Record analysis" })).toBeInTheDocument();
    unmount();
    mockBatch(makeBatch());
    renderWithProviders(<Pages />, { route: "/batches/b1" });
    expect(await screen.findByText(/once the batch is active/)).toBeInTheDocument();
  });

  it("links the profile name to its page, or says there is none", async () => {
    mockBatch(makeBatch({ quality_profile_id: "p1" }));
    const { unmount } = renderWithProviders(<Pages />, { route: "/batches/b1" });
    expect(await screen.findByRole("link", { name: "House lager" })).toHaveAttribute("href", "/quality-profiles/p1");
    unmount();
    mockBatch(makeBatch());
    renderWithProviders(<Pages />, { route: "/batches/b1" });
    expect(await screen.findByText("No quality profile")).toBeInTheDocument();
  });

  it("saves edits sending the current version", async () => {
    mockBatch(makeBatch({ version: 4 }));
    let body: Record<string, unknown> = {};
    server.use(
      http.patch(`${API_URL}/batches/b1`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(makeBatch({ beer_name: "Better Ale", version: 5 }));
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<Pages />, { route: "/batches/b1" });
    const name = await screen.findByLabelText("Beer name");
    await user.clear(name);
    await user.type(name, "Better Ale");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByRole("heading", { level: 2, name: "Better Ale" })).toBeInTheDocument();
    expect(body).toMatchObject({ beer_name: "Better Ale", version: 4 });
    expect(body).not.toHaveProperty("tank_id");
  });

  it("never flags its own save as changed elsewhere while lists and tanks refetch", async () => {
    mockBatch(makeBatch({ version: 4 }));
    server.use(
      http.patch(`${API_URL}/batches/b1`, () => HttpResponse.json(makeBatch({ beer_name: "Better Ale", version: 5 }))),
      http.get(`${API_URL}/tanks`, async () => {
        await delay(300);
        return HttpResponse.json([makeTank("tank-1"), makeTank("tank-2")]);
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<Pages />, { route: "/batches/b1" });
    const name = await screen.findByLabelText("Beer name");
    await user.clear(name);
    await user.type(name, "Better Ale");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    const deadline = Date.now() + 700;
    while (Date.now() < deadline) {
      expect(screen.queryByText(/changed elsewhere/)).not.toBeInTheDocument();
      await new Promise((resolve) => setTimeout(resolve, 10));
    }
    expect(screen.getByLabelText("Beer name")).toHaveValue("Better Ale");
  });

  it("tells the user to reload on a stale edit and reloads on request", async () => {
    mockBatch(makeBatch({ version: 4 }));
    server.use(
      http.patch(`${API_URL}/batches/b1`, () =>
        HttpResponse.json({ detail: [{ field: "version", message: "stale" }] }, { status: 409 }),
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(<Pages />, { route: "/batches/b1" });
    await user.click(await screen.findByRole("button", { name: "Save changes" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("This batch changed since you opened it. Reload it to see the latest version.");
    server.use(http.get(`${API_URL}/batches/b1`, () => HttpResponse.json(makeBatch({ beer_name: "Server Copy", version: 5 }))));
    await user.click(within(alert).getByRole("button", { name: "Reload batch" }));
    expect(await screen.findByRole("heading", { level: 2, name: "Server Copy" })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("retries loading the batch from the error state", async () => {
    mockCatalog();
    let calls = 0;
    server.use(
      http.get(`${API_URL}/batches/b1`, () => {
        calls += 1;
        return calls === 1 ? HttpResponse.json({ detail: [] }, { status: 500 }) : HttpResponse.json(makeBatch());
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<Pages />, { route: "/batches/b1" });
    await user.click(await screen.findByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { level: 2, name: "Pale Ale" })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("drops the errors of a failed save once a start succeeds", async () => {
    mockBatch(makeBatch());
    server.use(
      http.patch(`${API_URL}/batches/b1`, () =>
        HttpResponse.json({ detail: [{ field: "beer_name", message: "Bad name" }] }, { status: 422 }),
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(<Pages />, { route: "/batches/b1" });
    await user.click(await screen.findByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(screen.getByLabelText("Beer name")).toHaveAccessibleDescription("Bad name"));
    await user.click(screen.getByRole("button", { name: "Start batch" }));
    expect(await screen.findByText("Active")).toBeInTheDocument();
    expect(screen.getByLabelText("Beer name")).not.toHaveAttribute("aria-invalid");
    expect(screen.queryByText("Bad name")).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Tank")).not.toHaveFocus();
  });

  // Characterization: this already held with the remount-by-key approach and must keep holding.
  it("silently adopts a newer server copy when the form has no unsaved edits", async () => {
    mockBatch(makeBatch({ version: 4 }));
    const queryClient = createTestQueryClient();
    renderWithProviders(<Pages />, { route: "/batches/b1", queryClient });
    expect(await screen.findByLabelText("Beer name")).toHaveValue("Pale Ale");
    server.use(
      http.get(`${API_URL}/batches/b1`, () => HttpResponse.json(makeBatch({ beer_name: "Elsewhere", version: 5 }))),
    );
    await queryClient.invalidateQueries({ queryKey: batchKeys.detail("b1") });
    await waitFor(() => expect(screen.getByLabelText("Beer name")).toHaveValue("Elsewhere"));
    expect(screen.queryByText(/changed elsewhere/)).not.toBeInTheDocument();
  });

  it("keeps unsaved edits when the server copy changes underneath and offers a reload", async () => {
    mockBatch(makeBatch({ version: 4 }));
    const queryClient = createTestQueryClient();
    const user = userEvent.setup();
    renderWithProviders(<Pages />, { route: "/batches/b1", queryClient });
    const name = await screen.findByLabelText("Beer name");
    await user.clear(name);
    await user.type(name, "My edit");
    server.use(
      http.get(`${API_URL}/batches/b1`, () => HttpResponse.json(makeBatch({ beer_name: "Elsewhere", version: 5 }))),
    );
    await queryClient.invalidateQueries({ queryKey: batchKeys.detail("b1") });
    const notice = await screen.findByText(/This batch was changed elsewhere/);
    expect(notice).toHaveTextContent("your unsaved edits will be lost");
    expect(screen.getByLabelText("Beer name")).toHaveValue("My edit");
    await user.click(screen.getByRole("button", { name: "Reload" }));
    await waitFor(() => expect(screen.getByLabelText("Beer name")).toHaveValue("Elsewhere"));
    expect(screen.queryByText(/This batch was changed elsewhere/)).not.toBeInTheDocument();
  });

  it("shows no stale notice once the unsaved edits are reverted", async () => {
    mockBatch(makeBatch({ version: 4 }));
    const queryClient = createTestQueryClient();
    const user = userEvent.setup();
    renderWithProviders(<Pages />, { route: "/batches/b1", queryClient });
    const name = await screen.findByLabelText("Beer name");
    await user.type(name, "!");
    server.use(
      http.get(`${API_URL}/batches/b1`, () => HttpResponse.json(makeBatch({ beer_name: "Elsewhere", version: 5 }))),
    );
    await queryClient.invalidateQueries({ queryKey: batchKeys.detail("b1") });
    await screen.findByText(/This batch was changed elsewhere/);
    await user.type(screen.getByLabelText("Beer name"), "{Backspace}");
    await waitFor(() => expect(screen.getByLabelText("Beer name")).toHaveValue("Elsewhere"));
    expect(screen.queryByText(/This batch was changed elsewhere/)).not.toBeInTheDocument();
  });

  it("shows not found for an unknown batch", async () => {
    mockCatalog();
    server.use(
      http.get(`${API_URL}/batches/zzz`, () =>
        HttpResponse.json({ detail: [{ field: "batch_id", message: "nope" }] }, { status: 404 }),
      ),
    );
    renderWithProviders(<Pages />, { route: "/batches/zzz" });
    expect(await screen.findByRole("heading", { name: "Batch not found" })).toBeInTheDocument();
  });
});

describe("BatchesPage", () => {
  const batches = [
    makeBatch({ id: "b1", beer_name: "Pale Ale", status: "active", started_at: "2026-03-01T10:05:00Z" }),
    makeBatch({ id: "b2", beer_name: "Pils", tank_id: "tank-2", template: "lager" }),
  ];

  it("lists batches in a table with links to each one", async () => {
    mockCatalog();
    server.use(http.get(`${API_URL}/batches`, () => HttpResponse.json(batches)));
    renderWithProviders(<Pages />, { route: "/batches" });
    const table = await screen.findByRole("table", { name: "Batches" });
    expect(within(table).getByRole("link", { name: "Pale Ale" })).toHaveAttribute("href", "/batches/b1");
    expect(within(table).getByText("Active")).toBeInTheDocument();
    expect(within(table).getByText("Planned")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "New batch" })).toHaveAttribute("href", "/batches/new");
  });

  it("filters by tank and status through the query string", async () => {
    mockCatalog();
    const seen: string[] = [];
    server.use(
      http.get(`${API_URL}/batches`, ({ request }) => {
        seen.push(new URL(request.url).search);
        return HttpResponse.json(batches);
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<Pages />, { route: "/batches" });
    await screen.findByRole("table");
    await screen.findByRole("option", { name: "tank-2" });
    await user.selectOptions(screen.getByLabelText("Tank"), "tank-2");
    await user.selectOptions(screen.getByLabelText("Status"), "active");
    await waitFor(() => expect(seen.at(-1)).toBe("?tank_id=tank-2&status=active"));
    expect(seen[0]).toBe("");
  });

  it("shows an empty state", async () => {
    mockCatalog();
    server.use(http.get(`${API_URL}/batches`, () => HttpResponse.json([])));
    renderWithProviders(<Pages />, { route: "/batches" });
    expect(await screen.findByText("No batches match these filters")).toBeInTheDocument();
  });

  it("shows an error with retry", async () => {
    mockCatalog();
    server.use(http.get(`${API_URL}/batches`, () => HttpResponse.json({ detail: [] }, { status: 500 })));
    renderWithProviders(<Pages />, { route: "/batches" });
    expect(await screen.findByRole("alert")).toHaveTextContent("Request failed with status 500");
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("recovers when Try again succeeds", async () => {
    mockCatalog();
    let calls = 0;
    server.use(
      http.get(`${API_URL}/batches`, () => {
        calls += 1;
        return calls === 1 ? HttpResponse.json({ detail: [] }, { status: 500 }) : HttpResponse.json(batches);
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<Pages />, { route: "/batches" });
    await user.click(await screen.findByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("table", { name: "Batches" })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

describe("as a viewer", () => {
  const viewer = makeUser({ role: "viewer" });

  it("sees the batches but no way to create one", async () => {
    mockCatalog();
    server.use(http.get(`${API_URL}/batches`, () => HttpResponse.json([makeBatch()])));
    renderWithProviders(<Pages />, { route: "/batches", user: viewer });
    expect(await screen.findByRole("table", { name: "Batches" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "New batch" })).not.toBeInTheDocument();
  });

  it.each([
    ["planned", "Start batch"],
    ["active", "Finish batch"],
  ] as const)("cannot start, finish or edit a %s batch", async (status, action) => {
    mockCatalog();
    server.use(
      http.get(`${API_URL}/batches/b1`, () =>
        HttpResponse.json(makeBatch({ status, started_at: status === "active" ? "2026-03-01T10:05:00Z" : null })),
      ),
    );
    renderWithProviders(<Pages />, { route: "/batches/b1", user: viewer });
    expect(await screen.findByLabelText("Beer name")).toBeDisabled();
    expect(screen.queryByRole("button", { name: action })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save changes" })).not.toBeInTheDocument();
  });

  it("keeps the edit controls for a brewer", async () => {
    mockCatalog();
    server.use(http.get(`${API_URL}/batches/b1`, () => HttpResponse.json(makeBatch())));
    renderWithProviders(<Pages />, { route: "/batches/b1", user: makeUser({ role: "brewer" }) });
    expect(await screen.findByRole("button", { name: "Start batch" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save changes" })).toBeInTheDocument();
  });
});

describe("report downloads", () => {
  function mockBatchOf(overrides: Partial<Batch>) {
    mockCatalog();
    server.use(http.get(`${API_URL}/batches/b1`, () => HttpResponse.json(makeBatch(overrides))));
  }
  const active = { status: "active", started_at: "2026-03-01T10:05:00Z" } as const;
  const finished = { ...active, status: "finished", finished_at: "2026-03-05T10:00:00Z" } as const;

  it.each([
    ["active", active],
    ["finished", finished],
  ] as const)("offers the PDF and CSV of a %s batch", async (_status, overrides) => {
    mockBatchOf(overrides);
    renderWithProviders(<Pages />, { route: "/batches/b1" });
    expect(await screen.findByRole("link", { name: "Download PDF" })).toHaveAttribute(
      "href",
      `${API_URL}/batches/b1/report.pdf`,
    );
    expect(screen.getByRole("link", { name: "Download CSV" })).toHaveAttribute(
      "href",
      `${API_URL}/batches/b1/report.csv`,
    );
  });

  it("offers nothing for a planned batch", async () => {
    mockBatchOf({});
    renderWithProviders(<Pages />, { route: "/batches/b1" });
    await screen.findByLabelText("Beer name");
    expect(screen.queryByRole("link", { name: "Download PDF" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Download CSV" })).not.toBeInTheDocument();
  });

  it("says the report of an active batch is partial, and a finished one is not", async () => {
    mockBatchOf(active);
    const { unmount } = renderWithProviders(<Pages />, { route: "/batches/b1" });
    expect(await screen.findByText(/partial/i)).toBeInTheDocument();
    unmount();
    mockBatchOf(finished);
    renderWithProviders(<Pages />, { route: "/batches/b1" });
    await screen.findByRole("link", { name: "Download PDF" });
    expect(screen.queryByText(/partial/i)).not.toBeInTheDocument();
  });

  it("lets a viewer download", async () => {
    mockBatchOf(finished);
    renderWithProviders(<Pages />, { route: "/batches/b1", user: makeUser({ role: "viewer" }) });
    expect(await screen.findByRole("link", { name: "Download PDF" })).toBeInTheDocument();
  });
});
