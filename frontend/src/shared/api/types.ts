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

export type AlertKind = "out_of_range" | "silent_sensor";
export type AlertStatus = "open" | "acknowledged" | "resolved";

/** Known keys of `Alert.details`; the backend may add more, so unknown keys stay allowed. */
export interface AlertDetails {
  /** out_of_range: which limit was crossed. */
  bound?: "below" | "above";
  observed?: number;
  /** null when that side of the range is unbounded. */
  target_min?: number | null;
  target_max?: number | null;
  /** silent_sensor: ISO time of the last reading seen (null if the batch never reported). */
  last_reading_at?: string | null;
  /** Set only when the alert was closed by something other than recovery. */
  resolution?: "batch_finished" | "late_data";
  [key: string]: unknown;
}

export interface Alert {
  id: string;
  tank_id: string;
  batch_id: string;
  kind: AlertKind;
  measurement: Exclude<Measurement, "alcohol"> | null;
  status: AlertStatus;
  opened_at: string;
  acknowledged_at: string | null;
  resolved_at: string | null;
  details: AlertDetails;
  /** Optimistic-concurrency counter: grows with every change of the alert. */
  version: number;
}

/** One message of the `/ws/alerts` stream. */
export interface AlertEvent {
  type: "alert";
  alert: Alert;
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
