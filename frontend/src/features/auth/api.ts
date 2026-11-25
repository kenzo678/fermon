import type { QueryClient } from "@tanstack/react-query";
import { ApiError, apiGet, apiSend, apiSendEmpty } from "../../shared/api";
import type { User } from "../../shared/api";

export const sessionKeys = {
  all: ["session"] as const,
  current: () => [...sessionKeys.all, "current"] as const,
};

export interface Credentials {
  email: string;
  password: string;
}

export interface PasswordChange {
  current_password: string;
  new_password: string;
}

/** The signed-in user, or null when there is no (valid) session: that is an answer, not a failure. */
export async function fetchSession(signal?: AbortSignal): Promise<User | null> {
  try {
    return (await apiGet<{ user: User }>("/auth/me", { signal })).user;
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null;
    throw error;
  }
}

export async function login(credentials: Credentials): Promise<User> {
  return (await apiSend<{ user: User }>("POST", "/auth/login", credentials)).user;
}

export const logout = () => apiSendEmpty("POST", "/auth/logout");

export const changePassword = (body: PasswordChange) => apiSendEmpty("POST", "/auth/password", body);

/** Forgets everything fetched for a user so the next one never sees it, even for a moment. */
export function dropPrivateData(queryClient: QueryClient): void {
  void queryClient.cancelQueries({ predicate: (query) => query.queryKey[0] !== sessionKeys.all[0] });
  queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== sessionKeys.all[0] });
}

/**
 * Asks the server who we are now. Used when something suggests the session changed under us
 * (a 401, a forced password change, a closed socket): the answer, not the hint, is what counts.
 */
export function refreshSession(queryClient: QueryClient): Promise<User | null> {
  return queryClient
    .fetchQuery({
      queryKey: sessionKeys.current(),
      queryFn: ({ signal }) => fetchSession(signal),
      staleTime: 0,
    })
    .then((user) => {
      if (user === null) dropPrivateData(queryClient);
      return user;
    });
}
