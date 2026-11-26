import { ApiError } from "../../shared/api";
import type { Batch, BatchTemplate, BatchTemplateName, TargetRanges } from "../../shared/api";

/** Every input is a string while editing; conversion happens once, on submit. */
export interface FormValues {
  tank_id: string;
  template: BatchTemplateName | "";
  /** The profile's id; "" means none. */
  quality_profile_id: string;
  beer_name: string;
  style: string;
  planned_start: string;
  expected_end: string;
  notes: string;
  temperature_min: string;
  temperature_max: string;
  pressure_min: string;
  pressure_max: string;
  expected_final_abv: string;
}

export type FieldName = keyof FormValues;
export type FormErrors = Partial<Record<FieldName, string>>;

/** Visual order, used to focus the first invalid input. */
export const FIELD_ORDER: FieldName[] = [
  "tank_id",
  "template",
  "quality_profile_id",
  "beer_name",
  "style",
  "planned_start",
  "expected_end",
  "temperature_min",
  "temperature_max",
  "pressure_min",
  "pressure_max",
  "expected_final_abv",
  "notes",
];

const TARGET_FIELDS = [
  "temperature_min",
  "temperature_max",
  "pressure_min",
  "pressure_max",
  "expected_final_abv",
] as const satisfies readonly (keyof TargetRanges)[];
type TargetField = (typeof TARGET_FIELDS)[number];

const LIMITS: Record<TargetField, [number, number, string]> = {
  temperature_min: [-20, 100, "°C"],
  temperature_max: [-20, 100, "°C"],
  pressure_min: [0, 10, "bar"],
  pressure_max: [0, 10, "bar"],
  expected_final_abv: [0, 20, "% ABV"],
};
const REQUIRED_TARGETS: TargetField[] = ["temperature_min", "temperature_max", "pressure_max"];

export function emptyValues(plannedStart: string): FormValues {
  return {
    tank_id: "",
    template: "",
    quality_profile_id: "",
    beer_name: "",
    style: "",
    planned_start: plannedStart,
    expected_end: "",
    notes: "",
    temperature_min: "",
    temperature_max: "",
    pressure_min: "",
    pressure_max: "",
    expected_final_abv: "",
  };
}

const pad = (n: number) => String(n).padStart(2, "0");

/** ISO instant -> the browser-local `YYYY-MM-DDTHH:mm` a datetime-local input expects. */
export function toLocalInput(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** Local datetime-local value -> UTC ISO string, or null when it cannot be parsed. */
export function fromLocalInput(local: string): string | null {
  const d = new Date(local);
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
}

const isParseable = (local: string) => fromLocalInput(local) !== null;

const text = (value: number | null) => (value === null ? "" : String(value));

export function valuesFromBatch(batch: Batch): FormValues {
  const { targets } = batch;
  return {
    tank_id: batch.tank_id,
    template: batch.template,
    quality_profile_id: batch.quality_profile_id ?? "",
    beer_name: batch.beer_name,
    style: batch.style,
    planned_start: toLocalInput(batch.planned_start),
    expected_end: batch.expected_end === null ? "" : toLocalInput(batch.expected_end),
    notes: batch.notes ?? "",
    temperature_min: text(targets.temperature_min),
    temperature_max: text(targets.temperature_max),
    pressure_min: text(targets.pressure_min),
    pressure_max: text(targets.pressure_max),
    expected_final_abv: text(targets.expected_final_abv),
  };
}

/** A preset fills the target inputs (still editable); `custom` empties them. */
export function applyTemplate(
  values: FormValues,
  template: BatchTemplateName,
  templates: BatchTemplate[],
): FormValues {
  const preset = templates.find((t) => t.template === template)?.targets;
  return {
    ...values,
    template,
    temperature_min: text(preset?.temperature_min ?? null),
    temperature_max: text(preset?.temperature_max ?? null),
    pressure_min: text(preset?.pressure_min ?? null),
    pressure_max: text(preset?.pressure_max ?? null),
    expected_final_abv: text(preset?.expected_final_abv ?? null),
  };
}

function parseNumber(raw: string): number | null {
  if (raw.trim() === "") return null;
  const n = Number(raw);
  return Number.isFinite(n) ? n : Number.NaN;
}

/** Mirrors the backend rules so most mistakes are caught before the request. */
export function validate(values: FormValues): FormErrors {
  const errors: FormErrors = {};
  const required = (field: FieldName, message = "Required") => {
    if (values[field].trim() === "") errors[field] = message;
  };
  required("tank_id", "Choose a tank");
  required("template", "Choose a template");
  required("beer_name");
  required("style");
  required("planned_start");
  const INVALID_DATE = "Enter a valid date and time";
  if (errors.planned_start === undefined && !isParseable(values.planned_start)) errors.planned_start = INVALID_DATE;
  if (values.expected_end.trim() !== "" && !isParseable(values.expected_end)) errors.expected_end = INVALID_DATE;

  const numbers = {} as Record<TargetField, number | null>;
  for (const field of TARGET_FIELDS) {
    const value = parseNumber(values[field]);
    numbers[field] = value;
    const [min, max, unit] = LIMITS[field];
    if (value === null) {
      if (REQUIRED_TARGETS.includes(field)) errors[field] = "Required";
    } else if (Number.isNaN(value)) {
      errors[field] = "Enter a number";
    } else if (value < min || value > max) {
      errors[field] = `Must be between ${min} and ${max} ${unit}`;
    }
  }
  const { temperature_min: tMin, temperature_max: tMax, pressure_min: pMin, pressure_max: pMax } = numbers;
  if (errors.temperature_min === undefined && tMin !== null && tMax !== null && tMin >= tMax) {
    errors.temperature_min = "Must be lower than the maximum temperature";
  }
  if (errors.pressure_min === undefined && pMin !== null && pMax !== null && pMin >= pMax) {
    errors.pressure_min = "Must be lower than the maximum pressure";
  }
  if (
    errors.expected_end === undefined &&
    errors.planned_start === undefined &&
    values.expected_end !== "" &&
    values.planned_start !== "" &&
    Date.parse(values.expected_end) <= Date.parse(values.planned_start)
  ) {
    errors.expected_end = "Must be after the planned start";
  }
  return errors;
}

function targetsBody(values: FormValues, clearBlankOptionals: boolean): Partial<Record<TargetField, number | null>> {
  const targets: Partial<Record<TargetField, number | null>> = {};
  for (const field of TARGET_FIELDS) {
    const value = parseNumber(values[field]);
    if (value !== null) targets[field] = value;
    else if (clearBlankOptionals && !REQUIRED_TARGETS.includes(field)) targets[field] = null;
  }
  return targets;
}

export interface CreateBatchBody {
  tank_id: string;
  beer_name: string;
  style: string;
  template: BatchTemplateName;
  targets: Partial<Record<TargetField, number | null>>;
  planned_start: string;
  expected_end?: string;
  notes?: string;
  quality_profile_id?: string;
}

export function toCreateBody(values: FormValues): CreateBatchBody {
  const body: CreateBatchBody = {
    tank_id: values.tank_id,
    beer_name: values.beer_name.trim(),
    style: values.style.trim(),
    template: values.template as BatchTemplateName,
    targets: targetsBody(values, false),
    // validate() runs first; an unparseable value is sent as-is so the server rejects it rather than a throw.
    planned_start: fromLocalInput(values.planned_start) ?? values.planned_start,
  };
  const expectedEnd = fromLocalInput(values.expected_end);
  if (values.expected_end !== "") body.expected_end = expectedEnd ?? values.expected_end;
  if (values.notes.trim() !== "") body.notes = values.notes.trim();
  if (values.quality_profile_id !== "") body.quality_profile_id = values.quality_profile_id;
  return body;
}

export interface PatchBatchBody extends Omit<CreateBatchBody, "tank_id" | "expected_end" | "notes" | "quality_profile_id"> {
  expected_end: string | null;
  notes: string | null;
  quality_profile_id: string | null;
  version: number;
}

/** Sends every editable field so a cleared optional becomes an explicit null. */
export function toPatchBody(values: FormValues, version: number): PatchBatchBody {
  const create = toCreateBody(values);
  return {
    beer_name: create.beer_name,
    style: create.style,
    template: create.template,
    planned_start: create.planned_start,
    targets: targetsBody(values, true),
    expected_end: create.expected_end ?? null,
    notes: create.notes ?? null,
    quality_profile_id: create.quality_profile_id ?? null,
    version,
  };
}

export interface ServerErrors {
  fields: FormErrors;
  general: string[];
}

const CONFLICT_MESSAGES = {
  version: "This batch changed since you opened it. Reload it to see the latest version.",
  tank_id: "Another batch is already active in this tank.",
} as const;

/** Routes API error details to the input they name; everything else is a general message. */
export function mapServerErrors(error: Error): ServerErrors {
  const result: ServerErrors = { fields: {}, general: [] };
  if (!(error instanceof ApiError) || error.detail.length === 0) {
    result.general.push(error.message);
    return result;
  }
  for (const { field, message } of error.detail) {
    const name = field?.replace(/^targets\./, "") as FieldName | undefined;
    if (error.status === 409 && field === "version") result.general.push(CONFLICT_MESSAGES.version);
    else if (error.status === 409 && field === "tank_id") result.fields.tank_id = CONFLICT_MESSAGES.tank_id;
    else if (error.status === 409 && field === "status") {
      result.general.push(`This batch can't be changed from its current status: ${message}`);
    } else if (name !== undefined && FIELD_ORDER.includes(name) && result.fields[name] === undefined) {
      result.fields[name] = message;
    } else result.general.push(message);
  }
  return result;
}
