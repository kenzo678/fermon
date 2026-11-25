import { describe, expect, it } from "vitest";
import { ApiError } from "./errors";
import { fieldMessages } from "./formErrors";

describe("fieldMessages", () => {
  it("routes named fields to their input, keeping the first message of each", () => {
    const error = new ApiError(422, [
      { field: "email", message: "invalid email" },
      { field: "email", message: "second" },
      { field: "temporary_password", message: "too short" },
    ]);
    expect(fieldMessages(error)).toEqual({
      fields: { email: "invalid email", temporary_password: "too short" },
      general: [],
    });
  });

  it("puts details without a field, and plain errors, in the general list", () => {
    expect(fieldMessages(new ApiError(409, [{ field: null, message: "last admin" }]))).toEqual({
      fields: {},
      general: ["last admin"],
    });
    expect(fieldMessages(new Error("boom"))).toEqual({ fields: {}, general: ["boom"] });
    expect(fieldMessages(new ApiError(0, [], "Network error"))).toEqual({
      fields: {},
      general: ["Network error"],
    });
  });
});
