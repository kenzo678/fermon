import type { Bucket } from "../../shared/api";

export type RangeValue = "1h" | "6h" | "24h" | "7d";

interface RangeDefinition {
  value: RangeValue;
  label: string;
  windowMs: number;
  bucket: Bucket;
}

const HOUR_MS = 3_600_000;

const DEFINITIONS: Record<RangeValue, RangeDefinition> = {
  "1h": { value: "1h", label: "Last hour", windowMs: HOUR_MS, bucket: "1m" },
  "6h": { value: "6h", label: "Last 6 hours", windowMs: 6 * HOUR_MS, bucket: "1m" },
  "24h": { value: "24h", label: "Last 24 hours", windowMs: 24 * HOUR_MS, bucket: "1h" },
  "7d": { value: "7d", label: "Last 7 days", windowMs: 168 * HOUR_MS, bucket: "1h" },
};

/** Every option stays far below the backend's 10 000-point guard (max 360 points). */
export const RANGES: readonly RangeDefinition[] = Object.values(DEFINITIONS);

export const DEFAULT_RANGE: RangeValue = "24h";

export type AggregatedQuery = {
  bucket: Bucket;
  /** ISO-8601 UTC. */
  start: string;
  /** ISO-8601 UTC. */
  end: string;
};

export function rangeToQuery(range: RangeValue, now: number): AggregatedQuery {
  const definition = DEFINITIONS[range];
  return {
    bucket: definition.bucket,
    start: new Date(now - definition.windowMs).toISOString(),
    end: new Date(now).toISOString(),
  };
}

/** Parses a URL param; anything unknown falls back to the default range. */
export function parseRange(raw: string | null): RangeValue {
  return RANGES.find((r) => r.value === raw)?.value ?? DEFAULT_RANGE;
}
