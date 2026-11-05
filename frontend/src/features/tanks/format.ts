import type { Measurement, Reading } from "../../shared/api";

export const EMPTY_VALUE = "—";

interface MeasurementFormat {
  label: string;
  unit: string;
  decimals: number;
}

export const MEASUREMENTS: Record<Measurement, MeasurementFormat> = {
  temperature: { label: "Temperature", unit: "°C", decimals: 1 },
  pressure: { label: "Pressure", unit: "bar", decimals: 2 },
  alcohol: { label: "Alcohol", unit: "% ABV", decimals: 1 },
};

export const MEASUREMENT_ORDER: Measurement[] = ["temperature", "pressure", "alcohol"];

export function formatReading(measurement: Measurement, reading: Reading | null): string {
  if (!reading) return EMPTY_VALUE;
  const { unit, decimals } = MEASUREMENTS[measurement];
  const value = new Intl.NumberFormat("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(reading.value);
  return `${value} ${unit}`;
}

const dateTime = new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "short" });

/** Formats an ISO timestamp; a malformed one degrades to a dash instead of crashing the render. */
export function formatDateTime(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "—" : dateTime.format(date);
}

/** Newest valid recorded_at among the given readings; malformed timestamps are ignored. */
export function newestTimestamp(readings: (Reading | null)[]): string | null {
  let newest: string | null = null;
  let newestMs = Number.NEGATIVE_INFINITY;
  for (const reading of readings) {
    const ms = reading ? Date.parse(reading.recorded_at) : Number.NaN;
    // Malformed timestamps are skipped so they can never mask a valid, newer one.
    if (reading && !Number.isNaN(ms) && ms > newestMs) {
      newest = reading.recorded_at;
      newestMs = ms;
    }
  }
  return newest;
}
