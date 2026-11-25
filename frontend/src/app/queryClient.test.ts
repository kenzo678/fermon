import { waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { sessionKeys } from "../features/auth/api";
import { API_URL, ApiError, apiGet, apiSend } from "../shared/api";
import { makeUser } from "../test/fixtures";
import { server } from "../test/server";
import { createQueryClient, shouldRetry } from "./queryClient";

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

describe("session errors", () => {
  const sessionKey = sessionKeys.current();

  async function failWith(status: number, field: string | null) {
    const queryClient = createQueryClient({ retry: false });
    let sessionFetches = 0;
    server.use(
      http.get(`${API_URL}/auth/me`, () => {
        sessionFetches += 1;
        return HttpResponse.json({ user: makeUser({ must_change_password: true }) });
      }),
      http.get(`${API_URL}/tanks`, () =>
        HttpResponse.json({ detail: [{ field, message: "nope" }] }, { status }),
      ),
    );
    queryClient.setQueryData(sessionKey, makeUser());
    await queryClient.fetchQuery({ queryKey: ["tanks"], queryFn: () => apiGet("/tanks") }).catch(() => undefined);
    return { queryClient, fetches: () => sessionFetches };
  }

  it("a 401 on any query revalidates the session", async () => {
    const { fetches } = await failWith(401, null);
    await waitFor(() => expect(fetches()).toBe(1));
  });

  it("a 403 about the password revalidates the session (so the user is sent to change it)", async () => {
    const { queryClient, fetches } = await failWith(403, "password");
    await waitFor(() => expect(fetches()).toBe(1));
    await waitFor(() =>
      expect(queryClient.getQueryData<{ must_change_password: boolean }>(sessionKey)?.must_change_password).toBe(true),
    );
  });

  it("an ordinary 403 leaves the session alone", async () => {
    const { fetches } = await failWith(403, "role");
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(fetches()).toBe(0);
  });

  it("a failing mutation with 401 revalidates the session too", async () => {
    const queryClient = createQueryClient({ retry: false });
    let sessionFetches = 0;
    server.use(
      http.get(`${API_URL}/auth/me`, () => {
        sessionFetches += 1;
        return HttpResponse.json({ user: makeUser() });
      }),
      http.post(`${API_URL}/batches`, () => HttpResponse.json({ detail: [] }, { status: 401 })),
    );
    queryClient.setQueryData(sessionKey, makeUser());
    await queryClient
      .getMutationCache()
      .build(queryClient, { mutationFn: () => apiSend("POST", "/batches", {}) })
      .execute(undefined)
      .catch(() => undefined);
    await waitFor(() => expect(sessionFetches).toBe(1));
  });
});
