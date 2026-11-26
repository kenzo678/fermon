import { apiGet, apiSend } from "../../shared/api";
import type { LabAnalysis, QualityStage } from "../../shared/api";

export const labKeys = {
  all: ["lab-analyses"] as const,
  batch: (batchId: string) => [...labKeys.all, "batch", batchId] as const,
};

export interface CreateLabAnalysisBody {
  stage: QualityStage;
  /** Keyed by parameter code. */
  values: Record<string, number>;
  /** ISO instant; the server defaults to now. */
  sampled_at?: string;
  analyst?: string;
  notes?: string;
}

const batchPath = (batchId: string) => `/batches/${encodeURIComponent(batchId)}/lab-analyses`;

/** Oldest sample first, as the API returns them. */
export const fetchLabAnalyses = (batchId: string, stage?: QualityStage, signal?: AbortSignal) =>
  apiGet<LabAnalysis[]>(batchPath(batchId), { params: { stage }, signal });

export const fetchLabAnalysis = (analysisId: string, signal?: AbortSignal) =>
  apiGet<LabAnalysis>(`/lab-analyses/${encodeURIComponent(analysisId)}`, { signal });

export const createLabAnalysis = (batchId: string, body: CreateLabAnalysisBody) =>
  apiSend<LabAnalysis>("POST", batchPath(batchId), body);
