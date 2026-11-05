import { describe, expect, it } from "vitest";
import { formatDateTime } from "./format";

describe("formatDateTime", () => {
  it("formats a valid ISO timestamp", () => {
    expect(formatDateTime("2026-01-01T12:00:00Z")).toMatch(/2026/);
  });

  it("degrades to a dash instead of throwing on a malformed timestamp", () => {
    expect(formatDateTime("not-a-date")).toBe("—");
    expect(formatDateTime("")).toBe("—");
  });
});
