import { QueryClient } from "@tanstack/react-query";
import type { QueryClientConfig } from "@tanstack/react-query";
import { ApiError } from "../shared/api";

const MAX_RETRIES = 2;

/** Retry network and 5xx failures a couple of times; 4xx means the request itself is wrong. */
export function shouldRetry(failureCount: number, error: Error): boolean {
  if (error instanceof ApiError && error.status >= 400 && error.status < 500) return false;
  return failureCount < MAX_RETRIES;
}

export function createQueryClient(
  defaults: NonNullable<QueryClientConfig["defaultOptions"]>["queries"] = {},
): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: shouldRetry, refetchOnWindowFocus: true, ...defaults } },
  });
}
