import type { ErrorDetail } from "./types";

/** Status 0 means the request never got an HTTP response (network failure). */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: ErrorDetail[];
  /** Seconds from a `Retry-After` header (429), when the server sent a valid one. */
  readonly retryAfterSeconds: number | undefined;

  constructor(status: number, detail: ErrorDetail[], message?: string, retryAfterSeconds?: number) {
    super(message ?? detail[0]?.message ?? `Request failed with status ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.retryAfterSeconds = retryAfterSeconds;
  }
}
