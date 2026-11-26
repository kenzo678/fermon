import { describe, expect, it } from "vitest";
import type { LabResult, QualityStatus } from "../../shared/api";
import { STATUS_LABELS, summarize } from "./format";

const results = (...statuses: QualityStatus[]): LabResult[] =>
  statuses.map((status, i) => ({ parameter: `p${i}`, value: 1, unit: "", status }));

describe("summarize", () => {
  it.each([
    [["out_of_spec", "warning", "in_spec"], "1 out of spec, 1 warning"],
    [["warning", "warning"], "2 warnings"],
    [["out_of_spec", "out_of_spec", "no_spec"], "2 out of spec"],
    [["in_spec", "in_spec"], "All in spec"],
    [["in_spec", "no_spec"], "1 in spec, 1 without spec"],
    [["no_spec"], "No spec to compare with"],
  ] as const)("%j -> %s", (statuses, expected) => {
    expect(summarize(results(...statuses))).toBe(expected);
  });
});

describe("STATUS_LABELS", () => {
  it("names every status in words", () => {
    expect(STATUS_LABELS).toEqual({
      in_spec: "In spec",
      warning: "Warning",
      out_of_spec: "Out of spec",
      no_spec: "No spec",
    });
  });
});
