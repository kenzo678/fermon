import { API_URL, buildUrl } from "../api/client";

/**
 * Derives a WebSocket URL from the API base: http -> ws, https -> wss. An empty or relative base
 * resolves against the current page origin. Joining rules (path prefix, validation) are buildUrl's.
 */
export function wsUrlFor(path: string, base: string = API_URL): string {
  const httpUrl = new URL(buildUrl(path, undefined, base), window.location.origin);
  if (httpUrl.protocol === "http:") httpUrl.protocol = "ws:";
  else if (httpUrl.protocol === "https:") httpUrl.protocol = "wss:";
  return httpUrl.toString();
}
