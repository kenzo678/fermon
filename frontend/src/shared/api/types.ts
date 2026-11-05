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

export interface Tank {
  id: string;
  display_name: string | null;
  first_seen_at: string;
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
