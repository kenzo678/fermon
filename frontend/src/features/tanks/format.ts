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

/** Newest recorded_at among the given readings (ISO-8601 UTC strings compare chronologically). */
export function newestTimestamp(readings: (Reading | null)[]): string | null {
  let newest: string | null = null;
  for (const reading of readings) {
    if (reading && (newest === null || Date.parse(reading.recorded_at) > Date.parse(newest))) {
      newest = reading.recorded_at;
    }
  }
  return newest;
}
