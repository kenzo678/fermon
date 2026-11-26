import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { API_URL } from "../../shared/api";
import type { LabAnalysis } from "../../shared/api";
import {
  QUALITY_CATALOG,
  makeBatch,
  makeQualityProfile,
  makeQualitySpec,
  makeUser,
} from "../../test/fixtures";
import { renderWithProviders } from "../../test/renderWithProviders";
import { server } from "../../test/server";
import { LabAnalysesSection } from "./LabAnalysesSection";

const active = makeBatch({ status: "active", started_at: "2026-03-01T10:05:00Z", quality_profile_id: "p1" });
const profile = makeQualityProfile({
  id: "p1",
  specs: [
    makeQualitySpec({ stage: "brewhouse", parameter: "ph" }),
    makeQualitySpec({ stage: "brewhouse", parameter: "color" }),
    makeQualitySpec({ stage: "maturation", parameter: "original_extract" }),
  ],
});
const brewer = makeUser({ role: "brewer" });
const viewer = makeUser({ role: "viewer" });

function analysis(overrides: Partial<LabAnalysis> = {}): LabAnalysis {
  return {
    id: "l1",
    batch_id: "b1",
    stage: "brewhouse",
    sampled_at: "2026-03-02T09:30:00Z",
    created_at: "2026-03-02T09:45:00Z",
    analyst: "Ana",
    notes: "Second runnings",
    quality_profile_id: "p1",
    results: [
      { parameter: "ph", value: 5.9, unit: "pH", status: "out_of_spec" },
      { parameter: "color", value: 9, unit: "EBC", status: "warning" },
      { parameter: "wort_oxygen", value: 8, unit: "ppm", status: "in_spec" },
    ],
    ...overrides,
  };
}

function mockLab(analyses: LabAnalysis[] = []) {
  server.use(
    http.get(`${API_URL}/quality-parameters`, () => HttpResponse.json(QUALITY_CATALOG)),
    http.get(`${API_URL}/batches/b1/lab-analyses`, () => HttpResponse.json(analyses)),
  );
}

const renderSection = (options: { user?: ReturnType<typeof makeUser>; batch?: typeof active } = {}) =>
  renderWithProviders(<LabAnalysesSection batch={options.batch ?? active} profile={profile} />, {
    user: options.user ?? brewer,
  });

describe("LabAnalysesSection list", () => {
  it("only notes that analyses start with the batch while it is planned", () => {
    renderSection({ batch: makeBatch({ status: "planned" }) });
    expect(screen.getByText("Lab analyses can be recorded once the batch is active.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Record analysis" })).not.toBeInTheDocument();
  });

  it("groups analyses by stage with every value, its unit, a status badge and a summary", async () => {
    mockLab([analysis(), analysis({ id: "l2", stage: "maturation", results: [analysis().results[2]!] })]);
    renderSection({ user: viewer });
    const brewhouse = await screen.findByRole("region", { name: "Brewhouse (cold wort)" });
    expect(within(brewhouse).getByText("1 out of spec, 1 warning")).toBeInTheDocument();
    expect(within(brewhouse).getByText("Ana")).toBeInTheDocument();
    expect(within(brewhouse).getByText("Second runnings")).toBeInTheDocument();
    const row = within(brewhouse).getByRole("row", { name: /pH/ });
    expect(within(row).getByText("5.9 pH")).toBeInTheDocument();
    expect(within(row).getByText("Out of spec")).toBeInTheDocument();
    expect(within(brewhouse).getByRole("row", { name: /Color/ })).toHaveTextContent("Warning");
    expect(within(brewhouse).getByRole("row", { name: /Wort oxygen/ })).toHaveTextContent("In spec");
    const maturation = screen.getByRole("region", { name: "Maturation" });
    expect(within(maturation).getByText("All in spec")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Packaged" })).not.toBeInTheDocument();
  });

  it("colours the badges consistently", async () => {
    mockLab([analysis({ results: [
      { parameter: "ph", value: 5, unit: "pH", status: "in_spec" },
      { parameter: "color", value: 9, unit: "EBC", status: "warning" },
      { parameter: "wort_oxygen", value: 8, unit: "ppm", status: "out_of_spec" },
      { parameter: "original_extract", value: 8, unit: "°P", status: "no_spec" },
    ] })]);
    renderSection({ user: viewer });
    await screen.findByText("Second runnings");
    expect(screen.getByText("In spec")).toHaveClass("bg-emerald-100");
    expect(screen.getByText("Warning")).toHaveClass("bg-amber-100");
    expect(screen.getByText("Out of spec")).toHaveClass("bg-red-100");
    expect(screen.getByText("No spec")).toHaveClass("bg-slate-100");
  });

  it("shows an empty state, and viewers get no form", async () => {
    mockLab([]);
    renderSection({ user: viewer });
    expect(await screen.findByText("No analyses recorded yet")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Record analysis" })).not.toBeInTheDocument();
  });

  it("shows an error with retry", async () => {
    let calls = 0;
    server.use(
      http.get(`${API_URL}/quality-parameters`, () => HttpResponse.json(QUALITY_CATALOG)),
      http.get(`${API_URL}/batches/b1/lab-analyses`, () => {
        calls += 1;
        return calls === 1 ? HttpResponse.json({ detail: [] }, { status: 500 }) : HttpResponse.json([analysis()]);
      }),
    );
    const user = userEvent.setup();
    renderSection({ user: viewer });
    await user.click(await screen.findByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Second runnings")).toBeInTheDocument();
  });
});

describe("LabAnalysesSection record form", () => {
  async function openForm() {
    const user = userEvent.setup();
    renderSection();
    await user.click(await screen.findByRole("button", { name: "Record analysis" }));
    return user;
  }

  it("opens with the first stage, now as sampling time and the profile's parameters suggested", async () => {
    mockLab();
    await openForm();
    expect(screen.getByLabelText("Stage")).toHaveValue("brewhouse");
    expect((screen.getByLabelText("Sampled at") as HTMLInputElement).value).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/);
    expect(screen.getByLabelText("Parameter 1")).toHaveValue("ph");
    expect(screen.getByLabelText("Parameter 2")).toHaveValue("color");
    expect(screen.queryByLabelText("Parameter 3")).not.toBeInTheDocument();
  });

  it("swaps the suggestions with the stage until values are typed", async () => {
    mockLab();
    const user = await openForm();
    await user.selectOptions(screen.getByLabelText("Stage"), "maturation");
    expect(screen.getByLabelText("Parameter 1")).toHaveValue("original_extract");
    await user.selectOptions(screen.getByLabelText("Stage"), "packaged");
    expect(screen.getByLabelText("Parameter 1")).toHaveValue("");
    await user.selectOptions(screen.getByLabelText("Stage"), "brewhouse");
    await user.type(screen.getByLabelText("Value 1"), "5.2");
    await user.selectOptions(screen.getByLabelText("Stage"), "maturation");
    expect(screen.getByLabelText("Parameter 1")).toHaveValue("ph");
  });

  it("does not offer a parameter already chosen in another row", async () => {
    mockLab();
    const user = await openForm();
    await user.click(screen.getByRole("button", { name: "Add value" }));
    const third = screen.getByLabelText("Parameter 3");
    expect(within(third).queryByRole("option", { name: "pH" })).not.toBeInTheDocument();
    expect(within(third).queryByRole("option", { name: "Color" })).not.toBeInTheDocument();
    expect(within(third).getByRole("option", { name: "Wort oxygen" })).toBeInTheDocument();
    await user.click(screen.getAllByRole("button", { name: /^Remove value/ })[0]!);
    expect(within(screen.getByLabelText("Parameter 2")).getByRole("option", { name: "pH" })).toBeInTheDocument();
  });

  it("blocks a future sampling time and out-of-range values without sending anything", async () => {
    mockLab();
    let posted = false;
    server.use(http.post(`${API_URL}/batches/b1/lab-analyses`, () => ((posted = true), HttpResponse.json({}, { status: 201 }))));
    const user = await openForm();
    fireEvent.change(screen.getByLabelText("Sampled at"), { target: { value: "2099-01-01T10:00" } });
    await user.type(screen.getByLabelText("Value 1"), "15");
    await user.click(screen.getByRole("button", { name: "Save analysis" }));
    expect(screen.getByLabelText("Sampled at")).toHaveAccessibleDescription("Can't be in the future");
    expect(screen.getByLabelText("Value 1")).toHaveAccessibleDescription("Must be between 0 and 14 pH");
    expect(posted).toBe(false);
  });

  it("records the analysis, shows the evaluated statuses and closes the form", async () => {
    const recorded = analysis({ id: "l9", notes: "Fresh sample", results: [{ parameter: "ph", value: 5.3, unit: "pH", status: "in_spec" }] });
    mockLab();
    let body: Record<string, unknown> = {};
    server.use(
      http.post(`${API_URL}/batches/b1/lab-analyses`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        server.use(http.get(`${API_URL}/batches/b1/lab-analyses`, () => HttpResponse.json([recorded])));
        return HttpResponse.json(recorded, { status: 201 });
      }),
    );
    const user = await openForm();
    await user.type(screen.getByLabelText("Value 1"), "5.3");
    await user.type(screen.getByLabelText("Analyst"), "Ana");
    await user.click(screen.getByRole("button", { name: "Save analysis" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Analysis recorded");
    const group = await screen.findByRole("region", { name: "Brewhouse (cold wort)" });
    expect(within(group).getByText("Fresh sample")).toBeInTheDocument();
    expect(within(group).getByText("In spec")).toBeInTheDocument();
    expect(body).toMatchObject({ stage: "brewhouse", values: { ph: 5.3 }, analyst: "Ana" });
    expect(body).not.toHaveProperty("notes");
    expect((body as { sampled_at: string }).sampled_at).toMatch(/Z$/);
    expect(screen.queryByLabelText("Stage")).not.toBeInTheDocument();
  });

  it("maps 422 errors to the row and the date input", async () => {
    mockLab();
    server.use(
      http.post(`${API_URL}/batches/b1/lab-analyses`, () =>
        HttpResponse.json(
          {
            detail: [
              { field: "values.ph", message: "must be at most 14" },
              { field: "sampled_at", message: "must not be in the future" },
            ],
          },
          { status: 422 },
        ),
      ),
    );
    const user = await openForm();
    await user.type(screen.getByLabelText("Value 1"), "5.3");
    await user.click(screen.getByRole("button", { name: "Save analysis" }));
    await waitFor(() => expect(screen.getByLabelText("Value 1")).toHaveAccessibleDescription("must be at most 14"));
    expect(screen.getByLabelText("Sampled at")).toHaveAccessibleDescription("must not be in the future");
  });

  it("explains a 409 as a form-level message", async () => {
    mockLab();
    server.use(
      http.post(`${API_URL}/batches/b1/lab-analyses`, () =>
        HttpResponse.json({ detail: [{ field: "status", message: "planned batch" }] }, { status: 409 }),
      ),
    );
    const user = await openForm();
    await user.type(screen.getByLabelText("Value 1"), "5.3");
    await user.click(screen.getByRole("button", { name: "Save analysis" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Analyses can only be recorded once the batch is active");
  });

  it("can be cancelled", async () => {
    mockLab();
    const user = await openForm();
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByLabelText("Stage")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Record analysis" })).toBeInTheDocument();
  });
});
