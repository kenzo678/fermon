import type { ErrorDetail } from "./types";

/** Status 0 means the request never got an HTTP response (network failure). */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: ErrorDetail[];

  constructor(status: number, detail: ErrorDetail[], message?: string) {
    super(message ?? detail[0]?.message ?? `Request failed with status ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}
