import { ApiError } from "./errors";

export interface FieldMessages {
  /** First message per named field, for the input that owns it. */
  fields: Record<string, string>;
  /** Everything that names no field (or no known one), for a banner. */
  general: string[];
}

/** Splits an API failure into per-field messages and general ones. */
export function fieldMessages(error: Error): FieldMessages {
  const result: FieldMessages = { fields: {}, general: [] };
  if (!(error instanceof ApiError) || error.detail.length === 0) {
    result.general.push(error.message);
    return result;
  }
  for (const { field, message } of error.detail) {
    if (field === null) result.general.push(message);
    else result.fields[field] ??= message;
  }
  return result;
}
