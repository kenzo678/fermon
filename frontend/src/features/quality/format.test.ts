import { describe, expect, it } from "vitest";
import { STAGE_LABELS, STAGE_ORDER, formatRange, formatTarget, templateLabel } from "./format";

describe("quality format", () => {
  it("lists the stages in process order with human labels", () => {
    expect(STAGE_ORDER).toEqual(["brewhouse", "maturation", "bright_beer", "packaged"]);
    expect(STAGE_LABELS.brewhouse).toBe("Brewhouse (cold wort)");
    expect(STAGE_LABELS.bright_beer).toBe("Bright beer");
  });

  it("formats closed and half-open ranges with the unit", () => {
    expect(formatRange({ min: 4.15, max: 4.65 }, "pH")).toBe("4.15 – 4.65 pH");
    expect(formatRange({ min: null, max: 1 }, "ppm")).toBe("≤ 1 ppm");
    expect(formatRange({ min: 10, max: null }, "°P")).toBe("≥ 10 °P");
  });

  it("shows a dash for an absent range or target", () => {
    expect(formatRange(null, "pH")).toBe("—");
    expect(formatTarget(null, "pH")).toBe("—");
    expect(formatTarget(4.4, "pH")).toBe("4.4 pH");
  });

  it("makes a readable label from a template code", () => {
    expect(templateLabel("pale_lager")).toBe("Pale lager");
  });
});
