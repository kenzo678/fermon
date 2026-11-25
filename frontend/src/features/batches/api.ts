import { API_URL, apiGet, apiSend, buildUrl } from "../../shared/api";
import type { Batch, BatchStatus, BatchTemplate } from "../../shared/api";
import type { CreateBatchBody, PatchBatchBody } from "./form";

export interface BatchFilters {
  tank_id?: string;
  status?: BatchStatus;
}

export const batchKeys = {
  all: ["batches"] as const,
  lists: () => [...batchKeys.all, "list"] as const,
  list: (filters: BatchFilters) => [...batchKeys.lists(), filters] as const,
  detail: (batchId: string) => [...batchKeys.all, "detail", batchId] as const,
  templates: () => [...batchKeys.all, "templates"] as const,
};

const batchPath = (batchId: string) => `/batches/${encodeURIComponent(batchId)}`;

export function fetchBatches(filters: BatchFilters, signal?: AbortSignal): Promise<Batch[]> {
  return apiGet<Batch[]>("/batches", { params: { ...filters }, signal });
}

export function fetchBatch(batchId: string, signal?: AbortSignal): Promise<Batch> {
  return apiGet<Batch>(batchPath(batchId), { signal });
}

export function fetchBatchTemplates(signal?: AbortSignal): Promise<BatchTemplate[]> {
  return apiGet<BatchTemplate[]>("/batch-templates", { signal });
}

export const createBatch = (body: CreateBatchBody) => apiSend<Batch>("POST", "/batches", body);

export const updateBatch = (batchId: string, body: PatchBatchBody) =>
  apiSend<Batch>("PATCH", batchPath(batchId), body);

export const startBatch = (batchId: string) => apiSend<Batch>("POST", `${batchPath(batchId)}/start`);

export const finishBatch = (batchId: string) => apiSend<Batch>("POST", `${batchPath(batchId)}/finish`);

export type ReportFormat = "pdf" | "csv";

/**
 * Link target of a batch report. It is a plain URL, not a fetch: the browser sends the session cookie
 * on its own (same site in dev, same origin behind the e2e proxy) and streams the file to disk, and the
 * server's `Content-Disposition: attachment` forces the download even where `download` is ignored.
 */
export const reportUrl = (batchId: string, format: ReportFormat, base: string = API_URL): string =>
  buildUrl(`${batchPath(batchId)}/report.${format}`, undefined, base);
