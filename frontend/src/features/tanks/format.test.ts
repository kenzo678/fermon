import { describe, expect, it } from "vitest";
import { formatDateTime, newestTimestamp } from "./format";
import { makeReading } from "../../test/fixtures";

describe("formatDateTime", () => {
  it("formats a valid ISO timestamp", () => {
    expect(formatDateTime("2026-01-01T12:00:00Z")).toMatch(/2026/);
  });

  it("degrades to a dash instead of throwing on a malformed timestamp", () => {
    expect(formatDateTime("not-a-date")).toBe("—");
    expect(formatDateTime("")).toBe("—");
  });
});

describe("newestTimestamp", () => {
  it("ignores a malformed timestamp regardless of its position", () => {
    const bad = makeReading("tank-1", "temperature", 19, "garbage");
    const valid = makeReading("tank-1", "pressure", 1, "2026-01-01T12:00:00Z");
    const newer = makeReading("tank-1", "alcohol", 5, "2026-01-01T13:00:00Z");
    expect(newestTimestamp([bad, valid, newer])).toBe("2026-01-01T13:00:00Z");
    expect(newestTimestamp([valid, bad])).toBe("2026-01-01T12:00:00Z");
    expect(newestTimestamp([bad, null])).toBeNull();
  });
});
