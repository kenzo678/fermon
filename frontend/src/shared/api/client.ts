import { ApiError } from "./errors";
import type { ErrorDetail } from "./types";

export const API_URL: string = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

type ParamValue = string | number | undefined;
export interface RequestOptions {
  params?: Record<string, ParamValue | ParamValue[]>;
  signal?: AbortSignal;
}

const ABSOLUTE_URL = /^[a-z][a-z0-9+.-]*:\/\//i;

/**
 * Joins base and path without dropping a base path prefix. An empty or
 * relative base yields a relative URL (same origin). Invalid bases throw ApiError(0).
 */
export function buildUrl(
  path: string,
  params: RequestOptions["params"],
  base: string = API_URL,
): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params ?? {})) {
    for (const item of Array.isArray(value) ? value : [value]) {
      if (item !== undefined) query.append(key, String(item));
    }
  }
  const joined = `${base.replace(/\/+$/, "")}/${path.replace(/^\/+/, "")}`;
  const qs = query.toString();
  // A relative base must be empty or start with "/"; "host:port" without a scheme is a mistake,
  // not a path to resolve against the page origin.
  if (!ABSOLUTE_URL.test(base) && base !== "" && !base.startsWith("/")) {
    throw new ApiError(0, [], "Invalid API URL configuration");
  }
  try {
    const target = ABSOLUTE_URL.test(joined) ? new URL(joined).toString() : joined;
    return qs ? `${target}${target.includes("?") ? "&" : "?"}${qs}` : target;
  } catch {
    throw new ApiError(0, [], "Invalid API URL configuration");
  }
}

/** Aborts propagate as aborts (original reason), never as an ApiError, at any stage. */
function rethrowIfAborted(signal: AbortSignal | undefined, cause: unknown): void {
  if (signal?.aborted) throw signal.reason ?? cause;
}

async function readErrorDetail(response: Response, signal?: AbortSignal): Promise<ErrorDetail[]> {
  try {
    const body: unknown = await response.json();
    const detail = (body as { detail?: unknown }).detail;
    return Array.isArray(detail) ? (detail as ErrorDetail[]) : [];
  } catch (cause) {
    rethrowIfAborted(signal, cause);
    return [];
  }
}

export async function apiGet<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const url = buildUrl(path, options.params);
  let response: Response;
  try {
    response = await fetch(url, { signal: options.signal });
  } catch (cause) {
    rethrowIfAborted(options.signal, cause);
    throw new ApiError(0, [], "Network error: could not reach the API");
  }
  if (!response.ok) {
    throw new ApiError(response.status, await readErrorDetail(response, options.signal));
  }
  // Every endpoint we consume returns JSON, so an empty (204) or non-JSON 2xx body is an error.
  try {
    return (await response.json()) as T;
  } catch (cause) {
    rethrowIfAborted(options.signal, cause);
    throw new ApiError(response.status, [], "Invalid JSON response");
  }
}
