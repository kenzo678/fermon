import { describe, expect, it } from "vitest";
import { reportUrl } from "./api";

describe("reportUrl", () => {
  it("points at the report of the batch under the API base URL", () => {
    expect(reportUrl("b1", "pdf")).toBe("http://api.test/batches/b1/report.pdf");
    expect(reportUrl("b1", "csv")).toBe("http://api.test/batches/b1/report.csv");
  });

  it("keeps a path prefix in the base, as the e2e proxy uses", () => {
    expect(reportUrl("b1", "pdf", "/api")).toBe("/api/batches/b1/report.pdf");
    expect(reportUrl("b1", "csv", "/api/")).toBe("/api/batches/b1/report.csv");
  });

  it("escapes the batch id", () => {
    expect(reportUrl("a/b", "pdf", "")).toBe("/batches/a%2Fb/report.pdf");
  });
});
