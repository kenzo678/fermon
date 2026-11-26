import type { LabResult, QualityStatus } from "../../shared/api";

export const STATUS_LABELS: Record<QualityStatus, string> = {
  in_spec: "In spec",
  warning: "Warning",
  out_of_spec: "Out of spec",
  no_spec: "No spec",
};

/** Colour plus a text label (never colour alone): green, amber, red, grey. */
export const STATUS_STYLES: Record<QualityStatus, string> = {
  in_spec: "bg-emerald-100 text-emerald-800",
  warning: "bg-amber-100 text-amber-900",
  out_of_spec: "bg-red-100 text-red-800",
  no_spec: "bg-slate-100 text-slate-700",
};

/** "1 out of spec, 1 warning": what needs attention, else how well it went. */
export function summarize(results: LabResult[]): string {
  const count = (status: QualityStatus) => results.filter((r) => r.status === status).length;
  const outOfSpec = count("out_of_spec");
  const warnings = count("warning");
  const inSpec = count("in_spec");
  const noSpec = count("no_spec");
  const problems = [
    outOfSpec > 0 ? `${outOfSpec} out of spec` : null,
    warnings > 0 ? `${warnings} ${warnings === 1 ? "warning" : "warnings"}` : null,
  ].filter((part) => part !== null);
  if (problems.length > 0) return problems.join(", ");
  if (noSpec === 0) return "All in spec";
  if (inSpec === 0) return "No spec to compare with";
  return `${inSpec} in spec, ${noSpec} without spec`;
}
