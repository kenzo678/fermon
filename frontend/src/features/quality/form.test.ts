import { describe, expect, it } from "vitest";
import { ApiError } from "../../shared/api";
import type { QualityParameterInfo, QualitySpec } from "../../shared/api";
import { emptySpecValues, mapSpecErrors, toSpecBody, validateSpec, valuesFromSpec } from "./form";

const ph: QualityParameterInfo = { code: "ph", name: "pH", unit: "pH", minimum: 0, maximum: 14 };

const filled = (overrides = {}) => ({
  ...emptySpecValues(),
  stage: "bright_beer" as const,
  parameter: "ph",
  "acceptance.min": "4.1",
  "acceptance.max": "4.7",
  ...overrides,
});

describe("validateSpec", () => {
  it("accepts a consistent spec", () => {
    expect(validateSpec(filled({ "internal.min": "4.2", "internal.max": "4.6", target: "4.4" }), ph)).toEqual({});
  });

  it("requires a stage, a parameter and one acceptance bound", () => {
    const errors = validateSpec(emptySpecValues(), undefined);
    expect(errors.stage).toBeDefined();
    expect(errors.parameter).toBeDefined();
    expect(validateSpec(filled({ "acceptance.min": "", "acceptance.max": "" }), ph)["acceptance.min"]).toBe(
      "Enter a minimum, a maximum or both",
    );
  });

  it("keeps values inside the physical range of the parameter", () => {
    expect(validateSpec(filled({ "acceptance.max": "15" }), ph)["acceptance.max"]).toBe("Must be between 0 and 14");
  });

  it("rejects non-numbers and min not below max", () => {
    expect(validateSpec(filled({ "acceptance.min": "abc" }), ph)["acceptance.min"]).toBe("Must be a number");
    expect(validateSpec(filled({ "acceptance.min": "5" }), ph)["acceptance.max"]).toBe("Must be greater than min");
  });

  it("keeps the internal range inside acceptance and the target inside the tightest range", () => {
    expect(validateSpec(filled({ "internal.min": "4.0", "internal.max": "4.6" }), ph)["internal.min"]).toBe(
      "Must lie inside the acceptance range",
    );
    expect(validateSpec(filled({ "internal.max": "4.6" }), ph)["internal.min"]).toBe(
      "Must lie inside the acceptance range",
    );
    expect(validateSpec(filled({ "internal.min": "4.2", "internal.max": "4.6", target: "4.65" }), ph).target).toBe(
      "Must lie inside the internal range",
    );
  });
});

describe("toSpecBody", () => {
  it("sends null for blank optional parts", () => {
    expect(toSpecBody(filled())).toEqual({ acceptance: { min: 4.1, max: 4.7 }, internal: null, target: null });
    expect(toSpecBody(filled({ "acceptance.max": "", "internal.min": "4.2", target: "4.4" }))).toEqual({
      acceptance: { min: 4.1, max: null },
      internal: { min: 4.2, max: null },
      target: 4.4,
    });
  });
});

describe("valuesFromSpec", () => {
  it("round-trips a stored spec into editable strings", () => {
    const spec: QualitySpec = {
      stage: "packaged",
      parameter: "ph",
      unit: "pH",
      acceptance: { min: null, max: 4.7 },
      internal: { min: 4.2, max: 4.6 },
      target: null,
    };
    expect(valuesFromSpec(spec)).toMatchObject({
      stage: "packaged",
      "acceptance.min": "",
      "acceptance.max": "4.7",
      "internal.min": "4.2",
      target: "",
    });
  });
});

describe("mapSpecErrors", () => {
  it("routes named fields to inputs and the rest to a general message", () => {
    const error = new ApiError(422, [
      { field: "internal.min", message: "must lie inside the acceptance range" },
      { field: "acceptance", message: "needs at least one of min and max" },
      { field: null, message: "boom" },
    ]);
    expect(mapSpecErrors(error)).toEqual({
      fields: {
        "internal.min": "must lie inside the acceptance range",
        "acceptance.min": "needs at least one of min and max",
      },
      general: ["boom"],
    });
  });
});
