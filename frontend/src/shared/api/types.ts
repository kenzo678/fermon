export type Measurement = "temperature" | "pressure" | "alcohol";
export type Bucket = "1m" | "1h";

export interface Reading {
  tank_id: string;
  sensor_id: string;
  measurement: Measurement;
  value: number;
  unit: string;
  /** ISO-8601 UTC timestamp. */
  recorded_at: string;
}

/** Newest reading per measurement; null when the tank never reported it. */
export interface LatestReadings {
  temperature: Reading | null;
  pressure: Reading | null;
  alcohol: Reading | null;
}

export type BatchStatus = "planned" | "active" | "finished";
export type BatchTemplateName = "ale" | "lager" | "custom";

export interface TargetRanges {
  temperature_min: number;
  temperature_max: number;
  pressure_max: number;
  pressure_min: number | null;
  expected_final_abv: number | null;
}

export interface BatchTemplate {
  template: Exclude<BatchTemplateName, "custom">;
  targets: TargetRanges;
}

export interface Batch {
  id: string;
  tank_id: string;
  beer_name: string;
  style: string;
  template: BatchTemplateName;
  targets: TargetRanges;
  status: BatchStatus;
  planned_start: string;
  expected_end: string | null;
  started_at: string | null;
  finished_at: string | null;
  notes: string | null;
  created_at: string;
  /** Optimistic-concurrency counter: send it back on edits. */
  version: number;
}

/** The slice of an active batch embedded in a tank. */
export interface ActiveBatch {
  id: string;
  beer_name: string;
  style: string;
  targets: TargetRanges;
  started_at: string;
  expected_end: string | null;
}

export interface Tank {
  id: string;
  display_name: string | null;
  first_seen_at: string;
  active_batch: ActiveBatch | null;
  open_alerts: number;
  latest: LatestReadings;
}

export interface AggregatedPoint {
  bucket_start: string;
  avg: number;
  min: number;
  max: number;
  count: number;
}

export interface AggregatedReadings {
  tank_id: string;
  bucket: Bucket;
  /** One entry per requested measurement (empty list when it has no data). */
  series: Partial<Record<Measurement, AggregatedPoint[]>>;
}

export interface ErrorDetail {
  field: string | null;
  message: string;
}

export interface ErrorResponse {
  detail: ErrorDetail[];
}
