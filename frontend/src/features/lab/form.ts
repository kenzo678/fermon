import { ApiError } from "../../shared/api";
import type { QualityParameterInfo, QualityProfile, QualityStage } from "../../shared/api";
import { fromLocalInput } from "../batches/form";
import { STAGE_ORDER } from "../quality/format";
import type { CreateLabAnalysisBody } from "./api";

/** One parameter/value pair being typed; `id` keys the row, it is not sent. */
export interface ValueRow {
  id: string;
  parameter: string;
  value: string;
}

/** Every input is a string while editing; conversion happens once, on submit. */
export interface LabValues {
  stage: QualityStage;
  sampled_at: string;
  analyst: string;
  notes: string;
  rows: ValueRow[];
}

export type LabField = "stage" | "sampled_at" | "analyst" | "notes";
export interface RowErrors {
  parameter?: string;
  value?: string;
}
export interface LabErrors {
  fields: Partial<Record<LabField, string>>;
  /** By row id. */
  rows: Record<string, RowErrors>;
  /** Form-level messages: nothing in particular to point at. */
  general: string[];
}

let rowCounter = 0;
export const newRow = (): ValueRow => ({ id: `row-${++rowCounter}`, parameter: "", value: "" });

export const emptyValues = (sampledAt: string): LabValues => ({
  stage: STAGE_ORDER[0] as QualityStage,
  sampled_at: sampledAt,
  analyst: "",
  notes: "",
  rows: [newRow()],
});

export const emptyErrors = (): LabErrors => ({ fields: {}, rows: {}, general: [] });

export const hasErrors = (errors: LabErrors): boolean =>
  Object.keys(errors.fields).length > 0 || Object.keys(errors.rows).length > 0 || errors.general.length > 0;

export const hasTypedValue = (rows: ValueRow[]): boolean => rows.some((row) => row.value.trim() !== "");

/** A row with a parameter but no value is a suggestion the analyst skipped. */
const isFilled = (row: ValueRow) => row.parameter !== "" || row.value.trim() !== "";
const isMeasured = (row: ValueRow) => row.value.trim() !== "";

/** Mirrors the backend rules so most mistakes are caught before the request. */
export function validate(values: LabValues, catalog: QualityParameterInfo[], now: number): LabErrors {
  const errors = emptyErrors();
  if (values.sampled_at.trim() === "") errors.fields.sampled_at = "Required";
  else if (fromLocalInput(values.sampled_at) === null) errors.fields.sampled_at = "Enter a valid date and time";
  else if (Date.parse(values.sampled_at) > now) errors.fields.sampled_at = "Can't be in the future";

  const seen = new Set<string>();
  let measured = 0;
  for (const row of values.rows.filter(isFilled)) {
    const rowErrors: RowErrors = {};
    if (row.parameter === "") rowErrors.parameter = "Choose a parameter";
    else if (seen.has(row.parameter)) rowErrors.parameter = "Already added";
    else seen.add(row.parameter);
    if (isMeasured(row)) {
      measured += 1;
      const info = catalog.find((p) => p.code === row.parameter);
      const value = Number(row.value);
      if (!Number.isFinite(value)) rowErrors.value = "Enter a number";
      else if (info !== undefined && (value < info.minimum || value > info.maximum)) {
        rowErrors.value = `Must be between ${info.minimum} and ${info.maximum} ${info.unit}`.trimEnd();
      }
    }
    if (rowErrors.parameter !== undefined || rowErrors.value !== undefined) errors.rows[row.id] = rowErrors;
  }
  if (measured === 0) errors.general.push("Enter at least one value");
  return errors;
}

export function toBody(values: LabValues): CreateLabAnalysisBody {
  const body: CreateLabAnalysisBody = {
    stage: values.stage,
    // validate() runs first; an unparseable time is sent as-is so the server rejects it rather than a throw.
    sampled_at: fromLocalInput(values.sampled_at) ?? values.sampled_at,
    values: Object.fromEntries(
      values.rows.filter((row) => row.parameter !== "" && isMeasured(row)).map((row) => [row.parameter, Number(row.value)]),
    ),
  };
  if (values.analyst.trim() !== "") body.analyst = values.analyst.trim();
  if (values.notes.trim() !== "") body.notes = values.notes.trim();
  return body;
}

/** The parameters the profile specifies for `stage`, in catalog order, as empty rows to fill in. */
export function suggestedRows(
  profile: QualityProfile | undefined,
  stage: QualityStage,
  catalog: QualityParameterInfo[],
): ValueRow[] {
  const wanted = new Set(profile?.specs.filter((spec) => spec.stage === stage).map((spec) => spec.parameter));
  const rows = catalog
    .filter((info) => wanted.has(info.code))
    .map((info) => ({ id: `suggested-${info.code}`, parameter: info.code, value: "" }));
  // A stable id: this is recomputed while the analyst has not touched the rows yet.
  return rows.length > 0 ? rows : [{ id: "suggested-none", parameter: "", value: "" }];
}

const FIELDS: readonly string[] = ["stage", "sampled_at", "analyst", "notes"] satisfies LabField[];

/** Routes API error details to the input they name; everything else is a form-level message. */
export function mapServerErrors(error: Error, rows: ValueRow[]): LabErrors {
  const result = emptyErrors();
  if (!(error instanceof ApiError) || error.detail.length === 0) {
    result.general.push(error.message);
    return result;
  }
  for (const { field, message } of error.detail) {
    const code = field?.startsWith("values.") ? field.slice("values.".length) : undefined;
    const row = code === undefined ? undefined : rows.find((r) => r.parameter === code);
    if (error.status === 409 && field === "status") {
      result.general.push(`Analyses can only be recorded once the batch is active: ${message}`);
    } else if (row !== undefined) {
      result.rows[row.id] ??= { value: message };
    } else if (field !== null && FIELDS.includes(field)) {
      result.fields[field as LabField] ??= message;
    } else result.general.push(message);
  }
  return result;
}
