import type { QualityStage, SpecRange } from "../../shared/api";

/** Process order, as the API returns them. */
export const STAGE_ORDER: QualityStage[] = ["brewhouse", "maturation", "bright_beer", "packaged"];

export const STAGE_LABELS: Record<QualityStage, string> = {
  brewhouse: "Brewhouse (cold wort)",
  maturation: "Maturation",
  bright_beer: "Bright beer",
  packaged: "Packaged",
};

const withUnit = (text: string, unit: string) => (unit === "" ? text : `${text} ${unit}`);

/** "4.15 – 4.65 pH", "≤ 1 ppm", "≥ 10 °P"; "—" when there is no range at all. */
export function formatRange(range: SpecRange | null, unit: string): string {
  if (range === null || (range.min === null && range.max === null)) return "—";
  if (range.min !== null && range.max !== null) return withUnit(`${range.min} – ${range.max}`, unit);
  return withUnit(range.min !== null ? `≥ ${range.min}` : `≤ ${range.max}`, unit);
}

export const formatTarget = (target: number | null, unit: string): string =>
  target === null ? "—" : withUnit(String(target), unit);

/** "pale_lager" -> "Pale lager". */
export function templateLabel(template: string): string {
  const words = template.replaceAll("_", " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}
