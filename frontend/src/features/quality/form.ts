import { fieldMessages } from "../../shared/api";
import type { QualityParameterInfo, QualitySpec, QualityStage, SpecRange } from "../../shared/api";

/** Inputs are strings while editing; conversion happens once, on submit. Names match the API's fields. */
export interface SpecValues {
  stage: QualityStage | "";
  parameter: string;
  "acceptance.min": string;
  "acceptance.max": string;
  "internal.min": string;
  "internal.max": string;
  target: string;
}

export type SpecField = keyof SpecValues;
export type SpecErrors = Partial<Record<SpecField, string>>;

export interface SpecServerErrors {
  fields: SpecErrors;
  general: string[];
}

export interface SpecBody {
  acceptance: SpecRange;
  internal: SpecRange | null;
  target: number | null;
}

/** Visual order, used to focus the first invalid input. */
export const SPEC_FIELD_ORDER: SpecField[] = [
  "stage",
  "parameter",
  "acceptance.min",
  "acceptance.max",
  "internal.min",
  "internal.max",
  "target",
];

export const emptySpecValues = (): SpecValues => ({
  stage: "",
  parameter: "",
  "acceptance.min": "",
  "acceptance.max": "",
  "internal.min": "",
  "internal.max": "",
  target: "",
});

const text = (value: number | null) => (value === null ? "" : String(value));

export const valuesFromSpec = (spec: QualitySpec): SpecValues => ({
  stage: spec.stage,
  parameter: spec.parameter,
  "acceptance.min": text(spec.acceptance.min),
  "acceptance.max": text(spec.acceptance.max),
  "internal.min": text(spec.internal?.min ?? null),
  "internal.max": text(spec.internal?.max ?? null),
  target: text(spec.target),
});

const blank = (value: string) => value.trim() === "";
const parse = (value: string): number | null => (blank(value) ? null : Number(value));

/** The obvious rules, mirroring the domain; the server stays authoritative. */
export function validateSpec(values: SpecValues, parameter: QualityParameterInfo | undefined): SpecErrors {
  const errors: SpecErrors = {};
  if (values.stage === "") errors.stage = "Select a stage";
  if (parameter === undefined) errors.parameter = "Select a parameter";

  const numeric: SpecField[] = ["acceptance.min", "acceptance.max", "internal.min", "internal.max", "target"];
  for (const name of numeric) {
    const value = parse(values[name]);
    if (value === null) continue;
    if (!Number.isFinite(value)) errors[name] = "Must be a number";
    else if (parameter !== undefined && (value < parameter.minimum || value > parameter.maximum)) {
      errors[name] = `Must be between ${parameter.minimum} and ${parameter.maximum}`;
    }
  }

  const acceptance = { min: parse(values["acceptance.min"]), max: parse(values["acceptance.max"]) };
  const internal = { min: parse(values["internal.min"]), max: parse(values["internal.max"]) };
  const target = parse(values.target);
  if (acceptance.min === null && acceptance.max === null) {
    errors["acceptance.min"] ??= "Enter a minimum, a maximum or both";
  }
  for (const [kind, range] of [["acceptance", acceptance], ["internal", internal]] as const) {
    if (range.min !== null && range.max !== null && range.min >= range.max) {
      errors[`${kind}.max`] ??= "Must be greater than min";
    }
  }

  if (internal.min !== null || internal.max !== null) {
    // An open internal side is wider than any closed acceptance side.
    if (acceptance.min !== null && (internal.min === null || internal.min < acceptance.min)) {
      errors["internal.min"] ??= "Must lie inside the acceptance range";
    }
    if (acceptance.max !== null && (internal.max === null || internal.max > acceptance.max)) {
      errors["internal.max"] ??= "Must lie inside the acceptance range";
    }
  }
  if (target !== null) {
    const tightest = internal.min !== null || internal.max !== null ? internal : acceptance;
    if ((tightest.min !== null && target < tightest.min) || (tightest.max !== null && target > tightest.max)) {
      errors.target ??= "Must lie inside the internal range";
    }
  }
  return errors;
}

export function toSpecBody(values: SpecValues): SpecBody {
  const internal = { min: parse(values["internal.min"]), max: parse(values["internal.max"]) };
  return {
    acceptance: { min: parse(values["acceptance.min"]), max: parse(values["acceptance.max"]) },
    internal: internal.min === null && internal.max === null ? null : internal,
    target: parse(values.target),
  };
}

/** The API names a missing range by the range itself (`acceptance`); show it on the first input of it. */
const FIELD_ALIASES: Record<string, SpecField> = { acceptance: "acceptance.min", internal: "internal.min" };

/** Routes API error details to the input they name; everything else is a general message. */
export function mapSpecErrors(error: Error): SpecServerErrors {
  const { fields, general } = fieldMessages(error);
  const result: SpecServerErrors = { fields: {}, general: [...general] };
  for (const [field, message] of Object.entries(fields)) {
    const name = FIELD_ALIASES[field] ?? (SPEC_FIELD_ORDER.find((known) => known === field) as SpecField | undefined);
    if (name !== undefined && result.fields[name] === undefined) result.fields[name] = message;
    else result.general.push(message);
  }
  return result;
}
