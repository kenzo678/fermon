import { describe, expect, it } from "vitest";
import { DEFAULT_RANGE, RANGES, parseRange, rangeToQuery } from "./range";

const NOW = Date.parse("2026-03-10T12:00:00Z");
const MAX_POINTS = 10_000;
const BUCKET_MS = { "1m": 60_000, "1h": 3_600_000 };

describe("rangeToQuery", () => {
  it("maps every range to its window and bucket, ending at now", () => {
    expect(rangeToQuery("1h", NOW)).toEqual({
      bucket: "1m",
      start: "2026-03-10T11:00:00.000Z",
      end: "2026-03-10T12:00:00.000Z",
    });
    expect(rangeToQuery("6h", NOW)).toMatchObject({ bucket: "1m", start: "2026-03-10T06:00:00.000Z" });
    expect(rangeToQuery("24h", NOW)).toMatchObject({ bucket: "1h", start: "2026-03-09T12:00:00.000Z" });
    expect(rangeToQuery("7d", NOW)).toMatchObject({ bucket: "1h", start: "2026-03-03T12:00:00.000Z" });
  });

  it("stays within the backend point guard for every range", () => {
    for (const { value } of RANGES) {
      const { bucket, start, end } = rangeToQuery(value, NOW);
      expect((Date.parse(end) - Date.parse(start)) / BUCKET_MS[bucket]).toBeLessThanOrEqual(
        MAX_POINTS,
      );
    }
  });
});

describe("parseRange", () => {
  it("accepts known values", () => {
    expect(parseRange("7d")).toBe("7d");
    expect(parseRange("1h")).toBe("1h");
  });

  it("falls back to the default for missing or invalid values", () => {
    expect(parseRange(null)).toBe(DEFAULT_RANGE);
    expect(parseRange("")).toBe(DEFAULT_RANGE);
    expect(parseRange("30d")).toBe(DEFAULT_RANGE);
    expect(parseRange("toString")).toBe(DEFAULT_RANGE);
  });
});
