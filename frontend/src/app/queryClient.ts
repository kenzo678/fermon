import { MutationCache, QueryCache, QueryClient } from "@tanstack/react-query";
import type { QueryClientConfig } from "@tanstack/react-query";
import { refreshSession } from "../features/auth/api";
import { ApiError } from "../shared/api";

const MAX_RETRIES = 2;

/** Retry network and 5xx failures a couple of times; 4xx means the request itself is wrong. */
export function shouldRetry(failureCount: number, error: Error): boolean {
  if (error instanceof ApiError && error.status >= 400 && error.status < 500) return false;
  return failureCount < MAX_RETRIES;
}

/**
 * A 401 means the session ended; a 403 about `password` means it is a temporary one that must be
 * replaced first. Either way the server's answer on `/auth/me` decides where the user goes: the
 * route guards redirect from there. A 401 can also be a plain wrong password (login, password
 * change), in which case the session is still what it was and nothing changes.
 */
function revalidateSessionOn(error: unknown, queryClient: QueryClient): void {
  if (!(error instanceof ApiError)) return;
  const passwordRequired = error.status === 403 && error.detail.some((item) => item.field === "password");
  if (error.status === 401 || passwordRequired) void refreshSession(queryClient).catch(() => undefined);
}

export function createQueryClient(
  defaults: NonNullable<QueryClientConfig["defaultOptions"]>["queries"] = {},
): QueryClient {
  const queryClient: QueryClient = new QueryClient({
    // The session query reports 401 as "signed out", never as an error, so nothing here loops.
    queryCache: new QueryCache({ onError: (error) => revalidateSessionOn(error, queryClient) }),
    mutationCache: new MutationCache({ onError: (error) => revalidateSessionOn(error, queryClient) }),
    defaultOptions: { queries: { retry: shouldRetry, refetchOnWindowFocus: true, ...defaults } },
  });
  return queryClient;
}
