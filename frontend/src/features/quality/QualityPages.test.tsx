import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";
import { API_URL } from "../../shared/api";
import type { QualityProfile } from "../../shared/api";
import {
  QUALITY_CATALOG,
  makeQualityProfile,
  makeQualitySpec,
  makeUser,
} from "../../test/fixtures";
import { renderWithProviders } from "../../test/renderWithProviders";
import { server } from "../../test/server";
import { QualityProfileDetailPage } from "./QualityProfileDetailPage";
import { QualityProfilesPage } from "./QualityProfilesPage";

const viewer = makeUser({ role: "viewer" });
const brewer = makeUser({ role: "brewer" });

function Pages() {
  return (
    <Routes>
      <Route path="/quality-profiles" element={<QualityProfilesPage />} />
      <Route path="/quality-profiles/:profileId" element={<QualityProfileDetailPage />} />
    </Routes>
  );
}

function mockCatalog() {
  server.use(
    http.get(`${API_URL}/quality-parameters`, () => HttpResponse.json(QUALITY_CATALOG)),
    http.get(`${API_URL}/quality-profile-templates`, () =>
      HttpResponse.json([{ template: "pale_lager", specs: [makeQualitySpec()] }]),
    ),
  );
}

describe("QualityProfilesPage", () => {
  beforeEach(mockCatalog);
  const profiles = [
    makeQualityProfile({ id: "p1", name: "House lager", specs: [makeQualitySpec(), makeQualitySpec({ parameter: "color" })] }),
    makeQualityProfile({ id: "p2", name: "Empty" }),
  ];

  it("lists profiles by name with their spec counts, linking to the detail", async () => {
    server.use(http.get(`${API_URL}/quality-profiles`, () => HttpResponse.json(profiles)));
    renderWithProviders(<Pages />, { route: "/quality-profiles" });
    const table = await screen.findByRole("table", { name: "Quality profiles" });
    expect(within(table).getByRole("link", { name: "House lager" })).toHaveAttribute("href", "/quality-profiles/p1");
    expect(within(table).getByText("2 specs")).toBeInTheDocument();
    expect(within(table).getByText("0 specs")).toBeInTheDocument();
  });

  it("shows an empty state", async () => {
    server.use(http.get(`${API_URL}/quality-profiles`, () => HttpResponse.json([])));
    renderWithProviders(<Pages />, { route: "/quality-profiles" });
    expect(await screen.findByText("No quality profiles yet")).toBeInTheDocument();
  });

  it("shows an error state when the list fails", async () => {
    server.use(http.get(`${API_URL}/quality-profiles`, () => HttpResponse.json({ detail: [] }, { status: 500 })));
    renderWithProviders(<Pages />, { route: "/quality-profiles" });
    expect(await screen.findByRole("alert")).toHaveTextContent("Request failed with status 500");
  });

  it("offers no creation to a viewer", async () => {
    server.use(http.get(`${API_URL}/quality-profiles`, () => HttpResponse.json(profiles)));
    renderWithProviders(<Pages />, { route: "/quality-profiles", user: viewer });
    await screen.findByRole("table", { name: "Quality profiles" });
    expect(screen.queryByRole("button", { name: "New profile" })).not.toBeInTheDocument();
  });

  async function openForm(user: ReturnType<typeof userEvent.setup>) {
    await user.click(await screen.findByRole("button", { name: "New profile" }));
    await screen.findByRole("option", { name: "Pale lager" });
  }

  it("creates a profile from a template and opens it", async () => {
    mockCatalog();
    let body: unknown;
    const created = makeQualityProfile({ id: "p9", name: "My lager", specs: [makeQualitySpec()] });
    server.use(
      http.get(`${API_URL}/quality-profiles`, () => HttpResponse.json([])),
      http.post(`${API_URL}/quality-profiles`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(created, { status: 201 });
      }),
      http.get(`${API_URL}/quality-profiles/p9`, () => HttpResponse.json(created)),
    );
    const user = userEvent.setup();
    renderWithProviders(<Pages />, { route: "/quality-profiles", user: brewer });
    await openForm(user);
    await user.type(screen.getByLabelText("Name"), "My lager");
    await user.selectOptions(screen.getByLabelText("Template"), "pale_lager");
    await user.click(screen.getByRole("button", { name: "Create profile" }));
    expect(await screen.findByRole("heading", { level: 2, name: "My lager" })).toBeInTheDocument();
    expect(body).toEqual({ name: "My lager", template: "pale_lager" });
  });

  it("creates a blank profile without a template", async () => {
    mockCatalog();
    let body: unknown;
    const created = makeQualityProfile({ id: "p9", name: "Blank one" });
    server.use(
      http.get(`${API_URL}/quality-profiles`, () => HttpResponse.json([])),
      http.post(`${API_URL}/quality-profiles`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(created, { status: 201 });
      }),
      http.get(`${API_URL}/quality-profiles/p9`, () => HttpResponse.json(created)),
    );
    const user = userEvent.setup();
    renderWithProviders(<Pages />, { route: "/quality-profiles" });
    await openForm(user);
    expect(screen.getByLabelText("Template")).toHaveValue("");
    await user.type(screen.getByLabelText("Name"), "Blank one");
    await user.click(screen.getByRole("button", { name: "Create profile" }));
    await screen.findByRole("heading", { level: 2, name: "Blank one" });
    expect(body).toEqual({ name: "Blank one" });
  });

  it("requires a name", async () => {
    mockCatalog();
    server.use(http.get(`${API_URL}/quality-profiles`, () => HttpResponse.json([])));
    const user = userEvent.setup();
    renderWithProviders(<Pages />, { route: "/quality-profiles" });
    await openForm(user);
    await user.click(screen.getByRole("button", { name: "Create profile" }));
    expect(screen.getByLabelText("Name")).toHaveAccessibleDescription("Enter a name");
  });

  it("shows a duplicate name (409) on the name field", async () => {
    mockCatalog();
    server.use(
      http.get(`${API_URL}/quality-profiles`, () => HttpResponse.json([])),
      http.post(`${API_URL}/quality-profiles`, () =>
        HttpResponse.json({ detail: [{ field: "name", message: "A profile named 'House lager' already exists" }] }, { status: 409 }),
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(<Pages />, { route: "/quality-profiles" });
    await openForm(user);
    await user.type(screen.getByLabelText("Name"), "House lager");
    await user.click(screen.getByRole("button", { name: "Create profile" }));
    await waitFor(() =>
      expect(screen.getByLabelText("Name")).toHaveAccessibleDescription("A profile named 'House lager' already exists"),
    );
  });
});

describe("QualityProfileDetailPage", () => {
  beforeEach(mockCatalog);
  const specs = [
    makeQualitySpec({ stage: "packaged", parameter: "color", unit: "EBC", acceptance: { min: null, max: 10 }, internal: null, target: null }),
    makeQualitySpec(),
    makeQualitySpec({ stage: "brewhouse", parameter: "wort_oxygen", unit: "ppm", acceptance: { min: null, max: 8 }, internal: { min: null, max: 5 }, target: null }),
  ];

  /** A stateful fake of the API so a write is visible in the next read. */
  function serveProfile(initial: QualityProfile = makeQualityProfile({ specs })) {
    let profile = initial;
    const writes: Array<{ method: string; url: string; body: unknown }> = [];
    server.use(
      http.get(`${API_URL}/quality-profiles/p1`, () => HttpResponse.json(profile)),
      http.get(`${API_URL}/quality-profiles`, () => HttpResponse.json([profile])),
      http.put(`${API_URL}/quality-profiles/p1/specs/:stage/:parameter`, async ({ request, params }) => {
        const body = (await request.json()) as Pick<QualityProfile["specs"][number], "acceptance" | "internal" | "target">;
        writes.push({ method: "PUT", url: new URL(request.url).pathname, body });
        const spec = makeQualitySpec({ stage: params.stage as never, parameter: String(params.parameter), ...body });
        profile = { ...profile, specs: [...profile.specs.filter((s) => !(s.stage === spec.stage && s.parameter === spec.parameter)), spec] };
        return HttpResponse.json(spec);
      }),
      http.delete(`${API_URL}/quality-profiles/p1/specs/:stage/:parameter`, ({ request, params }) => {
        writes.push({ method: "DELETE", url: new URL(request.url).pathname, body: null });
        profile = { ...profile, specs: profile.specs.filter((s) => !(s.stage === params.stage && s.parameter === params.parameter)) };
        return new HttpResponse(null, { status: 204 });
      }),
    );
    return writes;
  }

  const stageTable = (label: string) => screen.findByRole("table", { name: label });

  it("groups specs by stage in process order with human labels", async () => {
    mockCatalog();
    serveProfile();
    renderWithProviders(<Pages />, { route: "/quality-profiles/p1" });
    const headings = await screen.findAllByRole("heading", { level: 3 });
    expect(headings.map((h) => h.textContent)).toEqual(["Brewhouse (cold wort)", "Maturation", "Bright beer", "Packaged"]);
    expect(await screen.findAllByText("No specs at this stage")).toHaveLength(2);
  });

  it("shows parameter, unit, ranges and target, with dashes for open sides", async () => {
    mockCatalog();
    serveProfile();
    renderWithProviders(<Pages />, { route: "/quality-profiles/p1" });
    const brewhouse = await stageTable("Brewhouse (cold wort)");
    const ph = within(within(brewhouse).getByRole("row", { name: /^pH/ }));
    expect(ph.getByText("5 – 5.6 pH")).toBeInTheDocument();
    expect(ph.getByText("5.1 – 5.5 pH")).toBeInTheDocument();
    expect(ph.getByText("5.3 pH")).toBeInTheDocument();
    const oxygen = within(within(brewhouse).getByRole("row", { name: /^Wort oxygen/ }));
    expect(oxygen.getByText("≤ 8 ppm")).toBeInTheDocument();
    expect(oxygen.getByText("≤ 5 ppm")).toBeInTheDocument();
    const packaged = within(within(await stageTable("Packaged")).getByRole("row", { name: /^Color/ }));
    expect(packaged.getAllByText("—")).toHaveLength(2);
  });

  it("is read-only for a viewer", async () => {
    mockCatalog();
    serveProfile();
    renderWithProviders(<Pages />, { route: "/quality-profiles/p1", user: viewer });
    await stageTable("Brewhouse (cold wort)");
    expect(screen.queryByRole("button", { name: /add specification/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Edit/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Delete/ })).not.toBeInTheDocument();
  });

  it("shows not found for an unknown profile", async () => {
    server.use(
      http.get(`${API_URL}/quality-profiles/p1`, () =>
        HttpResponse.json({ detail: [{ field: "profile_id", message: "nope" }] }, { status: 404 }),
      ),
    );
    renderWithProviders(<Pages />, { route: "/quality-profiles/p1" });
    expect(await screen.findByRole("heading", { name: "Quality profile not found" })).toBeInTheDocument();
  });

  async function openAdd(user: ReturnType<typeof userEvent.setup>) {
    await stageTable("Brewhouse (cold wort)");
    await user.click(screen.getByRole("button", { name: "Add specification" }));
  }

  it("adds a spec, offering only parameters not yet specified at the chosen stage", async () => {
    mockCatalog();
    const writes = serveProfile();
    const user = userEvent.setup();
    renderWithProviders(<Pages />, { route: "/quality-profiles/p1", user: brewer });
    await openAdd(user);
    await user.selectOptions(screen.getByLabelText("Stage"), "brewhouse");
    const parameter = screen.getByLabelText("Parameter");
    expect(within(parameter).queryByRole("option", { name: /^pH/ })).not.toBeInTheDocument();
    expect(within(parameter).getByRole("option", { name: /^Color/ })).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Stage"), "maturation");
    await user.selectOptions(parameter, "ph");
    await user.type(screen.getByLabelText("Acceptance min"), "4.1");
    await user.type(screen.getByLabelText("Acceptance max"), "4.7");
    await user.click(screen.getByRole("button", { name: "Save specification" }));
    const maturation = await stageTable("Maturation");
    expect(await within(maturation).findByText("4.1 – 4.7 pH")).toBeInTheDocument();
    expect(writes).toEqual([
      {
        method: "PUT",
        url: "/quality-profiles/p1/specs/maturation/ph",
        body: { acceptance: { min: 4.1, max: 4.7 }, internal: null, target: null },
      },
    ]);
    expect(screen.queryByRole("button", { name: "Save specification" })).not.toBeInTheDocument();
  });

  it("edits a spec in the form with stage and parameter fixed", async () => {
    mockCatalog();
    const writes = serveProfile();
    const user = userEvent.setup();
    renderWithProviders(<Pages />, { route: "/quality-profiles/p1", user: brewer });
    const brewhouse = await stageTable("Brewhouse (cold wort)");
    await user.click(within(brewhouse).getByRole("button", { name: "Edit pH" }));
    expect(screen.getByLabelText("Stage")).toBeDisabled();
    expect(screen.getByLabelText("Parameter")).toBeDisabled();
    expect(screen.getByLabelText("Acceptance max")).toHaveValue(5.6);
    await user.clear(screen.getByLabelText("Acceptance max"));
    await user.type(screen.getByLabelText("Acceptance max"), "5.8");
    await user.click(screen.getByRole("button", { name: "Save specification" }));
    expect(await within(await stageTable("Brewhouse (cold wort)")).findByText("5 – 5.8 pH")).toBeInTheDocument();
    expect(writes[0]).toMatchObject({ url: "/quality-profiles/p1/specs/brewhouse/ph", body: { acceptance: { min: 5, max: 5.8 } } });
  });

  it("deletes a spec only after confirmation", async () => {
    mockCatalog();
    const writes = serveProfile();
    const user = userEvent.setup();
    renderWithProviders(<Pages />, { route: "/quality-profiles/p1", user: brewer });
    const brewhouse = await stageTable("Brewhouse (cold wort)");
    await user.click(within(brewhouse).getByRole("button", { name: "Delete pH" }));
    await user.click(within(brewhouse).getByRole("button", { name: "Cancel" }));
    expect(writes).toEqual([]);
    await user.click(within(brewhouse).getByRole("button", { name: "Delete pH" }));
    await user.click(within(brewhouse).getByRole("button", { name: "Yes, delete pH" }));
    await waitFor(() => expect(within(screen.getByRole("table", { name: "Brewhouse (cold wort)" })).queryByRole("row", { name: /^pH/ })).not.toBeInTheDocument());
    expect(writes).toEqual([{ method: "DELETE", url: "/quality-profiles/p1/specs/brewhouse/ph", body: null }]);
  });

  it("maps a server 422 to the input it names", async () => {
    mockCatalog();
    serveProfile();
    server.use(
      http.put(`${API_URL}/quality-profiles/p1/specs/:stage/:parameter`, () =>
        HttpResponse.json({ detail: [{ field: "internal.min", message: "must lie inside the acceptance range" }] }, { status: 422 }),
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(<Pages />, { route: "/quality-profiles/p1", user: brewer });
    const brewhouse = await stageTable("Brewhouse (cold wort)");
    await user.click(within(brewhouse).getByRole("button", { name: "Edit pH" }));
    await user.click(screen.getByRole("button", { name: "Save specification" }));
    await waitFor(() =>
      expect(screen.getByLabelText("Internal min")).toHaveAccessibleDescription("must lie inside the acceptance range"),
    );
    // Editing the field dismisses its server message.
    await user.type(screen.getByLabelText("Internal min"), "1");
    expect(screen.getByLabelText("Internal min")).not.toHaveAccessibleDescription("must lie inside the acceptance range");
  });

  it("validates on the client before sending", async () => {
    mockCatalog();
    const writes = serveProfile();
    const user = userEvent.setup();
    renderWithProviders(<Pages />, { route: "/quality-profiles/p1", user: brewer });
    await openAdd(user);
    await user.selectOptions(screen.getByLabelText("Stage"), "maturation");
    await user.selectOptions(screen.getByLabelText("Parameter"), "ph");
    await user.type(screen.getByLabelText("Acceptance min"), "20");
    await user.click(screen.getByRole("button", { name: "Save specification" }));
    expect(screen.getByLabelText("Acceptance min")).toHaveAccessibleDescription("Must be between 0 and 14");
    expect(writes).toEqual([]);
  });
});
