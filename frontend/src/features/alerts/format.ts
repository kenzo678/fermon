import type { Alert, AlertKind, AlertStatus } from "../../shared/api";
import { MEASUREMENTS, formatDateTime } from "../tanks/format";

export const STATUS_LABELS: Record<AlertStatus, string> = {
  open: "Open",
  acknowledged: "Acknowledged",
  resolved: "Resolved",
};

export const STATUS_ORDER: AlertStatus[] = ["open", "acknowledged", "resolved"];

/** The statuses the API returns when no `status` filter is sent. */
export const UNRESOLVED: AlertStatus[] = ["open", "acknowledged"];

export const KIND_LABELS: Record<AlertKind, string> = {
  out_of_range: "Out of range",
  silent_sensor: "Silent sensor",
};

export const KIND_ORDER: AlertKind[] = ["out_of_range", "silent_sensor"];

const looseNumber = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });

function targetText(min: number | null | undefined, max: number | null | undefined, unit: string): string | null {
  if (typeof min === "number" && typeof max === "number") {
    return `${looseNumber.format(min)}–${looseNumber.format(max)} ${unit}`;
  }
  if (typeof max === "number") return `up to ${looseNumber.format(max)} ${unit}`;
  if (typeof min === "number") return `at least ${looseNumber.format(min)} ${unit}`;
  return null;
}

function outOfRangeMessage(alert: Alert): string {
  const format = alert.measurement === null ? undefined : MEASUREMENTS[alert.measurement];
  const label = format?.label ?? "Reading";
  const { bound, observed, target_min, target_max } = alert.details;
  if (format === undefined || (bound !== "below" && bound !== "above") || typeof observed !== "number") {
    return `${label} out of range`;
  }
  const seen = `observed ${observed.toFixed(format.decimals)} ${format.unit}`;
  const target = targetText(target_min, target_max, format.unit);
  return `${label} ${bound} target (${target === null ? seen : `${seen}, target ${target}`})`;
}

/** One human-readable sentence for the alert, built from its kind and details. */
export function alertMessage(alert: Alert): string {
  if (alert.kind === "silent_sensor") {
    const last = alert.details.last_reading_at;
    return typeof last === "string" ? `No readings since ${formatDateTime(last)}` : "No readings since the batch started";
  }
  return outOfRangeMessage(alert);
}

/** Only the resolutions that were not a plain recovery carry a note. */
export function resolutionNote(alert: Alert): string | null {
  if (alert.status !== "resolved") return null;
  if (alert.details.resolution === "batch_finished") return "Resolved because the batch was finished";
  if (alert.details.resolution === "late_data") return "Resolved by late-arriving data";
  return null;
}
