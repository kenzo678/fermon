import { describe, expect, it } from "vitest";
import { ApiError } from "../shared/api";
import { shouldRetry } from "./queryClient";

describe("shouldRetry", () => {
  it.each([400, 404, 422, 499])("never retries a %i ApiError", (status) => {
    expect(shouldRetry(0, new ApiError(status, []))).toBe(false);
  });

  it.each([0, 500, 503])("retries a %i failure at most twice", (status) => {
    const error = new ApiError(status, []);
    expect([0, 1, 2].map((count) => shouldRetry(count, error))).toEqual([true, true, false]);
  });

  it("retries a non-API error at most twice", () => {
    expect([0, 1, 2].map((count) => shouldRetry(count, new Error("x")))).toEqual([true, true, false]);
  });
});
