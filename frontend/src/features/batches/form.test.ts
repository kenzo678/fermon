import { describe, expect, it } from "vitest";
import { ApiError } from "../../shared/api";
import type { BatchTemplate } from "../../shared/api";
import { makeBatch } from "../../test/fixtures";
import {
  applyTemplate,
  emptyValues,
  fromLocalInput,
  mapServerErrors,
  toCreateBody,
  toLocalInput,
  toPatchBody,
  validate,
  valuesFromBatch,
} from "./form";
import type { FormValues } from "./form";

const templates: BatchTemplate[] = [
  {
    template: "ale",
    targets: { temperature_min: 18, temperature_max: 21, pressure_max: 1, pressure_min: null, expected_final_abv: 5 },
  },
];

function valid(overrides: Partial<FormValues> = {}): FormValues {
  return {
    ...emptyValues("2026-03-01T10:00"),
    tank_id: "tank-1",
    beer_name: "IPA",
    style: "American IPA",
    template: "custom",
    temperature_min: "17",
    temperature_max: "20",
    pressure_max: "1.5",
    ...overrides,
  };
}

describe("validate", () => {
  it("accepts a complete custom batch", () => {
    expect(validate(valid())).toEqual({});
  });

  it("requires tank, names, template and the three required targets", () => {
    const errors = validate(emptyValues("2026-03-01T10:00"));
    expect(Object.keys(errors).sort()).toEqual(
      ["beer_name", "pressure_max", "style", "tank_id", "temperature_max", "temperature_min", "template"].sort(),
    );
  });

  it("treats whitespace-only names as blank", () => {
    expect(validate(valid({ beer_name: "   " })).beer_name).toBeDefined();
  });

  it("requires temperature_min below temperature_max", () => {
    expect(validate(valid({ temperature_min: "20", temperature_max: "20" })).temperature_min).toMatch(/lower/);
  });

  it("requires pressure_min below pressure_max when given", () => {
    expect(validate(valid({ pressure_min: "2" })).pressure_min).toMatch(/lower/);
    expect(validate(valid({ pressure_min: "0.5" }))).toEqual({});
  });

  it("rejects non-numbers and out-of-range values", () => {
    expect(validate(valid({ temperature_max: "warm" })).temperature_max).toBeDefined();
    expect(validate(valid({ temperature_max: "101" })).temperature_max).toMatch(/100/);
    expect(validate(valid({ pressure_max: "11" })).pressure_max).toMatch(/10/);
    expect(validate(valid({ expected_final_abv: "21" })).expected_final_abv).toMatch(/20/);
  });

  it("requires the end to be after the start", () => {
    const errors = validate(valid({ planned_start: "2026-03-02T10:00", expected_end: "2026-03-01T10:00" }));
    expect(errors.expected_end).toMatch(/after/);
  });
});

describe("unparseable datetimes", () => {
  it("rejects an unparseable planned start and expected end", () => {
    const errors = validate(valid({ planned_start: "not-a-date", expected_end: "31/02/xx" }));
    expect(errors.planned_start).toBe("Enter a valid date and time");
    expect(errors.expected_end).toBe("Enter a valid date and time");
  });

  it("fromLocalInput returns null instead of throwing", () => {
    expect(fromLocalInput("not-a-date")).toBeNull();
    expect(fromLocalInput("")).toBeNull();
  });

  it("request builders never throw on unparseable input", () => {
    expect(() => toCreateBody(valid({ planned_start: "garbage", expected_end: "garbage" }))).not.toThrow();
    const values = valuesFromBatch(makeBatch());
    expect(() => toPatchBody({ ...values, planned_start: "garbage", expected_end: "garbage" }, 2)).not.toThrow();
  });
});

describe("applyTemplate", () => {
  it("prefills the targets from the preset", () => {
    const next = applyTemplate(valid(), "ale", templates);
    expect(next).toMatchObject({
      template: "ale",
      temperature_min: "18",
      temperature_max: "21",
      pressure_max: "1",
      pressure_min: "",
      expected_final_abv: "5",
    });
  });

  it("clears the targets for custom and keeps the rest", () => {
    const next = applyTemplate(valid({ template: "ale" }), "custom", templates);
    expect(next.template).toBe("custom");
    expect(next.temperature_min).toBe("");
    expect(next.beer_name).toBe("IPA");
  });
});

describe("request bodies", () => {
  it("builds a create body with UTC datetimes and omits blank optionals", () => {
    const body = toCreateBody(valid({ notes: "  ", pressure_min: "0.5" }));
    expect(body).toEqual({
      tank_id: "tank-1",
      beer_name: "IPA",
      style: "American IPA",
      template: "custom",
      targets: { temperature_min: 17, temperature_max: 20, pressure_max: 1.5, pressure_min: 0.5 },
      planned_start: new Date("2026-03-01T10:00").toISOString(),
    });
  });

  it("builds a patch body with the version and explicit nulls for cleared optionals", () => {
    const values = valuesFromBatch(makeBatch({ notes: "old", targets: { ...makeBatch().targets, pressure_min: 0.5 } }));
    const body = toPatchBody({ ...values, notes: "", pressure_min: "" }, 3);
    expect(body).toMatchObject({ version: 3, notes: null, expected_end: null });
    expect(body.targets).toMatchObject({ pressure_min: null, expected_final_abv: 5 });
    expect(body).not.toHaveProperty("tank_id");
  });
});

describe("local datetime conversion", () => {
  it("round-trips through the datetime-local format", () => {
    const iso = "2026-03-01T10:00:00.000Z";
    expect(fromLocalInput(toLocalInput(iso))).toBe(iso);
  });
});

describe("mapServerErrors", () => {
  it("maps nested and bare target fields to their inputs", () => {
    const error = new ApiError(422, [
      { field: "targets.temperature_min", message: "too cold" },
      { field: "pressure_min", message: "must be lower" },
    ]);
    expect(mapServerErrors(error)).toEqual({
      fields: { temperature_min: "too cold", pressure_min: "must be lower" },
      general: [],
    });
  });

  it("keeps messages for unknown or missing fields as general errors", () => {
    const error = new ApiError(422, [
      { field: null, message: "malformed" },
      { field: "created_at", message: "nope" },
    ]);
    expect(mapServerErrors(error).general).toEqual(["malformed", "nope"]);
  });

  it("explains version and status conflicts", () => {
    const stale = mapServerErrors(new ApiError(409, [{ field: "version", message: "x" }]));
    expect(stale.general).toEqual(["This batch changed since you opened it. Reload it to see the latest version."]);
    const finished = mapServerErrors(new ApiError(409, [{ field: "status", message: "finished batch" }]));
    expect(finished.general).toEqual(["This batch can't be changed from its current status: finished batch"]);
  });

  it("explains an active-batch conflict next to the tank", () => {
    const result = mapServerErrors(new ApiError(409, [{ field: "tank_id", message: "x" }]));
    expect(result.fields.tank_id).toBe("Another batch is already active in this tank.");
  });
});
