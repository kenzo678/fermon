import type { BatchStatus, TargetRanges } from "../../shared/api";

export const STATUS_LABELS: Record<BatchStatus, string> = {
  planned: "Planned",
  active: "Active",
  finished: "Finished",
};

export const STATUS_ORDER: BatchStatus[] = ["planned", "active", "finished"];

const number = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });

/** "18–21 °C", for the temperature band of a batch. */
export function formatTemperatureRange(targets: Pick<TargetRanges, "temperature_min" | "temperature_max">): string {
  return `${number.format(targets.temperature_min)}–${number.format(targets.temperature_max)} °C`;
}

/** "up to 1 bar", or "0.5–1 bar" when a minimum is set. */
export function formatPressureRange(targets: Pick<TargetRanges, "pressure_min" | "pressure_max">): string {
  const max = number.format(targets.pressure_max);
  return targets.pressure_min === null
    ? `up to ${max} bar`
    : `${number.format(targets.pressure_min)}–${max} bar`;
}
