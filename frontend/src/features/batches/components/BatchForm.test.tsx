import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { BatchTemplate } from "../../../shared/api";
import { makeBatch, makeTank } from "../../../test/fixtures";
import { renderWithProviders } from "../../../test/renderWithProviders";
import { emptyValues, valuesFromBatch } from "../form";
import type { ServerErrors } from "../form";
import { BatchForm } from "./BatchForm";

const tanks = [makeTank("tank-1"), makeTank("tank-2", { display_name: "Lager tank" })];
const templates: BatchTemplate[] = [
  {
    template: "ale",
    targets: { temperature_min: 18, temperature_max: 21, pressure_max: 1, pressure_min: null, expected_final_abv: 5 },
  },
];

function setup(props: Partial<React.ComponentProps<typeof BatchForm>> = {}) {
  const onSubmit = vi.fn();
  renderWithProviders(
    <BatchForm
      mode="create"
      initialValues={emptyValues("2026-03-01T10:00")}
      tanks={tanks}
      templates={templates}
      submitLabel="Create batch"
      submitting={false}
      serverErrors={null}
      onSubmit={onSubmit}
      {...props}
    />,
  );
  return onSubmit;
}

async function fillRequired(user: ReturnType<typeof userEvent.setup>) {
  await user.selectOptions(screen.getByLabelText("Tank"), "tank-1");
  await user.type(screen.getByLabelText("Beer name"), "Pale Ale");
  await user.type(screen.getByLabelText("Style"), "APA");
}

describe("BatchForm", () => {
  it("labels every input and shows units on the targets", () => {
    setup();
    for (const label of [
      "Tank",
      "Template",
      "Beer name",
      "Style",
      "Planned start",
      "Expected end",
      "Notes",
      "Minimum temperature (°C)",
      "Maximum temperature (°C)",
      "Minimum pressure (bar)",
      "Maximum pressure (bar)",
      "Expected final ABV (%)",
    ]) {
      expect(screen.getByLabelText(label)).toBeInTheDocument();
    }
    expect(screen.getByRole("option", { name: "Lager tank" })).toBeInTheDocument();
  });

  it("prefills the targets from a template and empties them for custom", async () => {
    const user = userEvent.setup();
    setup();
    await user.selectOptions(screen.getByLabelText("Template"), "ale");
    expect(screen.getByLabelText("Minimum temperature (°C)")).toHaveValue(18);
    expect(screen.getByLabelText("Maximum pressure (bar)")).toHaveValue(1);
    await user.selectOptions(screen.getByLabelText("Template"), "custom");
    expect(screen.getByLabelText("Minimum temperature (°C)")).toHaveValue(null);
  });

  it("blocks an invalid submit, links errors with aria-describedby and focuses the first invalid input", async () => {
    const user = userEvent.setup();
    const onSubmit = setup();
    await user.click(screen.getByRole("button", { name: "Create batch" }));
    expect(onSubmit).not.toHaveBeenCalled();
    const tank = screen.getByLabelText("Tank");
    expect(tank).toHaveFocus();
    expect(tank).toHaveAttribute("aria-invalid", "true");
    expect(tank).toHaveAccessibleDescription("Choose a tank");
  });

  it("submits the values once valid", async () => {
    const user = userEvent.setup();
    const onSubmit = setup();
    await fillRequired(user);
    await user.selectOptions(screen.getByLabelText("Template"), "ale");
    await user.click(screen.getByRole("button", { name: "Create batch" }));
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ tank_id: "tank-1", template: "ale", beer_name: "Pale Ale", temperature_max: "21" }),
    );
  });

  it("shows the min < max rule next to the input", async () => {
    const user = userEvent.setup();
    const onSubmit = setup();
    await fillRequired(user);
    await user.selectOptions(screen.getByLabelText("Template"), "ale");
    await user.clear(screen.getByLabelText("Minimum temperature (°C)"));
    await user.type(screen.getByLabelText("Minimum temperature (°C)"), "25");
    await user.click(screen.getByRole("button", { name: "Create batch" }));
    expect(screen.getByLabelText("Minimum temperature (°C)")).toHaveAccessibleDescription(
      "Must be lower than the maximum temperature",
    );
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("renders server field errors next to the right input and general ones in an alert", () => {
    const serverErrors: ServerErrors = {
      fields: { temperature_max: "Out of physical range", tank_id: "Another batch is already active in this tank." },
      general: ["This batch changed since you opened it. Reload it to see the latest version."],
    };
    setup({ serverErrors });
    expect(screen.getByLabelText("Maximum temperature (°C)")).toHaveAccessibleDescription("Out of physical range");
    expect(screen.getByLabelText("Tank")).toHaveAccessibleDescription(
      "Another batch is already active in this tank.",
    );
    expect(screen.getByRole("alert")).toHaveTextContent("changed since you opened it");
    expect(screen.getByLabelText("Tank")).toHaveFocus();
  });

  it("clears a field's server error as soon as that field is edited", async () => {
    const user = userEvent.setup();
    setup({ serverErrors: { fields: { beer_name: "Bad name", style: "Bad style" }, general: [] } });
    await user.type(screen.getByLabelText("Beer name"), "x");
    expect(screen.getByLabelText("Beer name")).not.toHaveAttribute("aria-invalid");
    expect(screen.getByLabelText("Beer name")).not.toHaveAccessibleDescription("Bad name");
    expect(screen.getByLabelText("Style")).toHaveAccessibleDescription("Bad style");
  });

  it("choosing a template clears only the target and template errors", async () => {
    const user = userEvent.setup();
    setup({
      serverErrors: {
        fields: { beer_name: "Bad name", temperature_max: "Out of range", template: "Bad template" },
        general: [],
      },
    });
    await user.selectOptions(screen.getByLabelText("Template"), "ale");
    expect(screen.getByLabelText("Maximum temperature (°C)")).not.toHaveAttribute("aria-invalid");
    expect(screen.getByLabelText("Template")).not.toHaveAttribute("aria-invalid");
    expect(screen.getByLabelText("Beer name")).toHaveAccessibleDescription("Bad name");
  });

  it("choosing a template keeps unrelated client errors", async () => {
    const user = userEvent.setup();
    setup();
    await user.click(screen.getByRole("button", { name: "Create batch" }));
    expect(screen.getByLabelText("Beer name")).toHaveAccessibleDescription("Required");
    await user.selectOptions(screen.getByLabelText("Template"), "ale");
    expect(screen.getByLabelText("Beer name")).toHaveAccessibleDescription("Required");
    expect(screen.getByLabelText("Template")).not.toHaveAttribute("aria-invalid");
  });

  it("locks the tank when editing and disables everything when read-only", () => {
    setup({ mode: "edit", initialValues: valuesFromBatch(makeBatch()), submitLabel: "Save changes" });
    expect(screen.getByLabelText("Tank")).toBeDisabled();
    expect(screen.getByLabelText("Beer name")).toBeEnabled();
  });

  it("is read-only without a submit button for a finished batch", () => {
    setup({ mode: "edit", readOnly: true, initialValues: valuesFromBatch(makeBatch({ status: "finished" })) });
    expect(screen.getByLabelText("Beer name")).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Create batch" })).not.toBeInTheDocument();
  });

  it("disables the submit button while submitting", () => {
    setup({ submitting: true });
    expect(screen.getByRole("button", { name: "Saving…" })).toBeDisabled();
  });
});
