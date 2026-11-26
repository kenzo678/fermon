import { describe, expect, it } from "vitest";
import { ApiError } from "../../shared/api";
import { QUALITY_CATALOG, makeQualityProfile, makeQualitySpec } from "../../test/fixtures";
import { emptyValues, hasErrors, mapServerErrors, suggestedRows, toBody, validate } from "./form";
import type { LabValues } from "./form";

const NOW = Date.parse("2026-03-02T12:00:00");

function valid(overrides: Partial<LabValues> = {}): LabValues {
  return {
    ...emptyValues("2026-03-02T11:30"),
    rows: [{ id: "r1", parameter: "ph", value: "5.3" }],
    ...overrides,
  };
}

describe("emptyValues", () => {
  it("starts at the first stage, sampled when given, with one empty row", () => {
    const values = emptyValues("2026-03-02T11:30");
    expect(values).toMatchObject({ stage: "brewhouse", sampled_at: "2026-03-02T11:30", analyst: "", notes: "" });
    expect(values.rows).toHaveLength(1);
    expect(values.rows[0]).toMatchObject({ parameter: "", value: "" });
  });
});

describe("validate", () => {
  it("accepts a complete analysis", () => {
    expect(hasErrors(validate(valid(), QUALITY_CATALOG, NOW))).toBe(false);
  });

  it("rejects a sample taken in the future", () => {
    const errors = validate(valid({ sampled_at: "2026-03-02T12:01" }), QUALITY_CATALOG, NOW);
    expect(errors.fields.sampled_at).toBe("Can't be in the future");
  });

  it("requires a parseable sampling time", () => {
    expect(validate(valid({ sampled_at: "" }), QUALITY_CATALOG, NOW).fields.sampled_at).toBe("Required");
    expect(validate(valid({ sampled_at: "garbage" }), QUALITY_CATALOG, NOW).fields.sampled_at).toBe(
      "Enter a valid date and time",
    );
  });

  it("needs at least one value", () => {
    const errors = validate(valid({ rows: [{ id: "r1", parameter: "", value: "" }] }), QUALITY_CATALOG, NOW);
    expect(errors.general).toEqual(["Enter at least one value"]);
  });

  it("skips rows left blank but wants a parameter for a value", () => {
    const rows = [
      { id: "r1", parameter: "ph", value: "" },
      { id: "r2", parameter: "", value: "4" },
      { id: "r3", parameter: "color", value: "8" },
    ];
    const errors = validate(valid({ rows }), QUALITY_CATALOG, NOW);
    expect(errors.rows).toEqual({ r2: { parameter: "Choose a parameter" } });
  });

  it("checks numbers against the physical limits of the parameter", () => {
    const rows = [
      { id: "r1", parameter: "ph", value: "15" },
      { id: "r2", parameter: "color", value: "abc" },
    ];
    const errors = validate(valid({ rows }), QUALITY_CATALOG, NOW);
    expect(errors.rows.r1?.value).toBe("Must be between 0 and 14 pH");
    expect(errors.rows.r2?.value).toBe("Enter a number");
  });

  it("flags a parameter that appears twice", () => {
    const rows = [
      { id: "r1", parameter: "ph", value: "5" },
      { id: "r2", parameter: "ph", value: "6" },
    ];
    const errors = validate(valid({ rows }), QUALITY_CATALOG, NOW);
    expect(errors.rows.r2?.parameter).toBe("Already added");
    expect(errors.rows.r1).toBeUndefined();
  });
});

describe("toBody", () => {
  it("sends UTC time, trimmed optionals and the values by code, skipping blank rows", () => {
    const body = toBody(
      valid({
        analyst: " Ana ",
        notes: "  ",
        rows: [
          { id: "r1", parameter: "ph", value: "5.3" },
          { id: "r2", parameter: "color", value: "" },
        ],
      }),
    );
    expect(body).toEqual({
      stage: "brewhouse",
      sampled_at: new Date("2026-03-02T11:30").toISOString(),
      analyst: "Ana",
      values: { ph: 5.3 },
    });
  });
});

describe("suggestedRows", () => {
  const profile = makeQualityProfile({
    specs: [
      makeQualitySpec({ stage: "brewhouse", parameter: "ph" }),
      makeQualitySpec({ stage: "brewhouse", parameter: "color" }),
      makeQualitySpec({ stage: "maturation", parameter: "ph" }),
    ],
  });

  it("proposes the parameters the profile specifies for the stage, in catalog order", () => {
    const rows = suggestedRows(profile, "brewhouse", QUALITY_CATALOG);
    expect(rows.map((r) => [r.parameter, r.value])).toEqual([
      ["ph", ""],
      ["color", ""],
    ]);
  });

  it("falls back to one empty row without a profile or specs for the stage", () => {
    expect(suggestedRows(undefined, "brewhouse", QUALITY_CATALOG).map((r) => r.parameter)).toEqual([""]);
    expect(suggestedRows(profile, "packaged", QUALITY_CATALOG).map((r) => r.parameter)).toEqual([""]);
  });
});

describe("mapServerErrors", () => {
  const rows = [
    { id: "r1", parameter: "ph", value: "20" },
    { id: "r2", parameter: "color", value: "8" },
  ];

  it("routes values.<code> to its row and sampled_at to its input", () => {
    const error = new ApiError(422, [
      { field: "values.ph", message: "must be at most 14" },
      { field: "sampled_at", message: "must not be in the future" },
      { field: "stage", message: "is not a quality stage" },
    ]);
    expect(mapServerErrors(error, rows)).toEqual({
      fields: { sampled_at: "must not be in the future", stage: "is not a quality stage" },
      rows: { r1: { value: "must be at most 14" } },
      general: [],
    });
  });

  it("explains a planned batch as a form-level message", () => {
    const error = new ApiError(409, [{ field: "status", message: "planned batch cannot analyze" }]);
    expect(mapServerErrors(error, rows).general).toEqual([
      "Analyses can only be recorded once the batch is active: planned batch cannot analyze",
    ]);
  });

  it("keeps everything else as general messages", () => {
    const error = new ApiError(404, [{ field: "batch_id", message: "batch not found" }]);
    expect(mapServerErrors(error, rows).general).toEqual(["batch not found"]);
    expect(mapServerErrors(new Error("boom"), rows).general).toEqual(["boom"]);
    const unknown = new ApiError(422, [{ field: "values.nope", message: "is not a known parameter" }]);
    expect(mapServerErrors(unknown, rows).general).toEqual(["is not a known parameter"]);
  });
});
