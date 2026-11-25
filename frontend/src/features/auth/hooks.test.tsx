import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { API_URL } from "../../shared/api";
import { makeUser } from "../../test/fixtures";
import { createTestQueryClient } from "../../test/renderWithProviders";
import { server } from "../../test/server";
import { sessionKeys } from "./api";
import { useLogin, useLogout, usePermissions, useSession } from "./hooks";

function setup() {
  const queryClient = createTestQueryClient();
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return { queryClient, wrapper };
}

describe("useSession", () => {
  it("returns the signed-in user", async () => {
    server.use(http.get(`${API_URL}/auth/me`, () => HttpResponse.json({ user: makeUser() })));
    const { wrapper } = setup();
    const { result } = renderHook(() => useSession(), { wrapper });
    await waitFor(() => expect(result.current.data).toMatchObject({ email: "admin@example.com" }));
  });

  it("resolves to null (not an error) when there is no session", async () => {
    server.use(
      http.get(`${API_URL}/auth/me`, () =>
        HttpResponse.json({ detail: [{ field: null, message: "authentication required" }] }, { status: 401 }),
      ),
    );
    const { wrapper } = setup();
    const { result } = renderHook(() => useSession(), { wrapper });
    await waitFor(() => expect(result.current.data).toBeNull());
    expect(result.current.isError).toBe(false);
  });

  it("surfaces other failures as errors", async () => {
    server.use(http.get(`${API_URL}/auth/me`, () => HttpResponse.json({}, { status: 500 })));
    const { wrapper } = setup();
    const { result } = renderHook(() => useSession(), { wrapper });
    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

describe("usePermissions", () => {
  it("derives the abilities from the cached role and denies everything without a session", () => {
    const { queryClient, wrapper } = setup();
    queryClient.setQueryData(sessionKeys.current(), makeUser({ role: "viewer" }));
    const viewer = renderHook(() => usePermissions(), { wrapper });
    expect(viewer.result.current).toMatchObject({ canWriteBatches: false, canManageUsers: false });

    queryClient.setQueryData(sessionKeys.current(), makeUser({ role: "brewer" }));
    const brewer = renderHook(() => usePermissions(), { wrapper });
    expect(brewer.result.current).toMatchObject({ canWriteBatches: true, canManageUsers: false });

    queryClient.setQueryData(sessionKeys.current(), null);
    const anonymous = renderHook(() => usePermissions(), { wrapper });
    expect(anonymous.result.current).toMatchObject({ canWriteBatches: false, canAcknowledgeAlerts: false });
  });
});

describe("useLogin / useLogout", () => {
  it("login stores the user and drops data cached for a previous session", async () => {
    server.use(
      http.post(`${API_URL}/auth/login`, () => HttpResponse.json({ user: makeUser({ email: "b@example.com" }) })),
    );
    const { queryClient, wrapper } = setup();
    queryClient.setQueryData(["tanks"], ["stale"]);
    const { result } = renderHook(() => useLogin(), { wrapper });
    await act(() => result.current.mutateAsync({ email: "b@example.com", password: "pw" }));
    expect(queryClient.getQueryData(sessionKeys.current())).toMatchObject({ email: "b@example.com" });
    expect(queryClient.getQueryData(["tanks"])).toBeUndefined();
  });

  it("logout clears the session and every cached query", async () => {
    server.use(http.post(`${API_URL}/auth/logout`, () => new HttpResponse(null, { status: 204 })));
    const { queryClient, wrapper } = setup();
    queryClient.setQueryData(sessionKeys.current(), makeUser());
    queryClient.setQueryData(["tanks"], ["private"]);
    const { result } = renderHook(() => useLogout(), { wrapper });
    await act(() => result.current.mutateAsync());
    expect(queryClient.getQueryData(sessionKeys.current())).toBeNull();
    expect(queryClient.getQueryData(["tanks"])).toBeUndefined();
  });
});
