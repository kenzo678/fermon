import { useMemo, useState } from "react";
import type { FormEvent } from "react";
import type { LabAnalysis, QualityParameterInfo, QualityProfile, QualityStage } from "../../../shared/api";
import { Field, controlClass } from "../../batches/components/Field";
import { toLocalInput } from "../../batches/form";
import { STAGE_LABELS, STAGE_ORDER } from "../../quality/format";
import { primaryButton, secondaryButton } from "../../quality/components/buttons";
import {
  emptyErrors,
  emptyValues,
  hasErrors,
  hasTypedValue,
  mapServerErrors,
  newRow,
  suggestedRows,
  toBody,
  validate,
} from "../form";
import type { LabErrors, LabField, ValueRow } from "../form";
import { useRecordLabAnalysis } from "../hooks";

interface RecordAnalysisFormProps {
  batchId: string;
  profile: QualityProfile | undefined;
  catalog: QualityParameterInfo[];
  onRecorded: (analysis: LabAnalysis) => void;
  onCancel: () => void;
}

export function RecordAnalysisForm({ batchId, profile, catalog, onRecorded, onCancel }: RecordAnalysisFormProps) {
  const record = useRecordLabAnalysis(batchId);
  // The default sampling time is "now"; computed once so the form's state is stable.
  const [values, setValues] = useState(() => emptyValues(toLocalInput(new Date().toISOString())));
  // null: the rows are still the profile's suggestions for the stage; any edit takes them over.
  const [typedRows, setTypedRows] = useState<ValueRow[] | null>(null);
  const [errors, setErrors] = useState<LabErrors>(emptyErrors);
  const suggestions = useMemo(() => suggestedRows(profile, values.stage, catalog), [profile, values.stage, catalog]);
  const rows = typedRows ?? suggestions;

  const setField = (name: LabField, value: string) => {
    setValues((current) => ({ ...current, [name]: value }));
    setErrors((current) => ({ ...current, fields: { ...current.fields, [name]: undefined } }));
  };
  const changeStage = (stage: QualityStage) => {
    setField("stage", stage);
    // Suggestions follow the stage until the analyst has typed values worth keeping.
    if (typedRows !== null && !hasTypedValue(typedRows)) setTypedRows(null);
  };
  const changeRow = (id: string, change: Partial<ValueRow>) => {
    setTypedRows(rows.map((row) => (row.id === id ? { ...row, ...change } : row)));
    setErrors((current) => ({ ...current, rows: { ...current.rows, [id]: {} } }));
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const submitted = { ...values, rows };
    const found = validate(submitted, catalog, Date.now());
    setErrors(found);
    if (hasErrors(found)) return;
    record.mutate(toBody(submitted), {
      onSuccess: onRecorded,
      onError: (error) => setErrors(mapServerErrors(error, rows)),
    });
  };

  return (
    <form onSubmit={submit} noValidate className="space-y-4 rounded-lg border border-slate-200 bg-white p-4">
      <h4 className="text-sm font-semibold text-slate-900">Record analysis</h4>
      {errors.general.length > 0 && (
        <div role="alert" className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-900">
          {errors.general.map((message) => (
            <p key={message}>{message}</p>
          ))}
        </div>
      )}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label="Stage" error={errors.fields.stage}>
          <select value={values.stage} onChange={(e) => changeStage(e.target.value as QualityStage)} className={controlClass}>
            {STAGE_ORDER.map((stage) => (
              <option key={stage} value={stage}>
                {STAGE_LABELS[stage]}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Sampled at" error={errors.fields.sampled_at}>
          <input
            type="datetime-local"
            value={values.sampled_at}
            onChange={(e) => setField("sampled_at", e.target.value)}
            className={controlClass}
          />
        </Field>
        <Field label="Analyst" error={errors.fields.analyst}>
          <input type="text" value={values.analyst} onChange={(e) => setField("analyst", e.target.value)} className={controlClass} />
        </Field>
        <Field label="Notes" error={errors.fields.notes}>
          <input type="text" value={values.notes} onChange={(e) => setField("notes", e.target.value)} className={controlClass} />
        </Field>
      </div>
      <fieldset className="space-y-3">
        <legend className="text-sm font-semibold text-slate-900">Values</legend>
        {rows.map((row, index) => {
          const taken = new Set(rows.filter((other) => other.id !== row.id).map((other) => other.parameter));
          const info = catalog.find((p) => p.code === row.parameter);
          const rowErrors = errors.rows[row.id];
          const errorId = `${row.id}-error`;
          const message = rowErrors?.parameter ?? rowErrors?.value;
          return (
            <div key={row.id} className="space-y-1">
              <div className="grid grid-cols-[1fr_auto] items-center gap-2 sm:grid-cols-[2fr_1fr_auto_auto]">
                <select
                  aria-label={`Parameter ${index + 1}`}
                  aria-invalid={rowErrors?.parameter !== undefined ? true : undefined}
                  aria-describedby={rowErrors?.parameter !== undefined ? errorId : undefined}
                  value={row.parameter}
                  onChange={(e) => changeRow(row.id, { parameter: e.target.value })}
                  className={`${controlClass} col-span-2 sm:col-span-1`}
                >
                  <option value="">Select a parameter</option>
                  {catalog
                    .filter((p) => !taken.has(p.code))
                    .map((p) => (
                      <option key={p.code} value={p.code}>
                        {p.name}
                      </option>
                    ))}
                </select>
                <input
                  type="number"
                  step="any"
                  inputMode="decimal"
                  aria-label={`Value ${index + 1}`}
                  aria-invalid={rowErrors?.value !== undefined ? true : undefined}
                  aria-describedby={rowErrors?.value !== undefined ? errorId : undefined}
                  value={row.value}
                  onChange={(e) => changeRow(row.id, { value: e.target.value })}
                  className={controlClass}
                />
                <span className="min-w-12 text-sm text-slate-600">{info?.unit ?? ""}</span>
                <button
                  type="button"
                  aria-label={`Remove value ${index + 1}`}
                  onClick={() => setTypedRows(rows.filter((other) => other.id !== row.id))}
                  className={secondaryButton}
                >
                  Remove
                </button>
              </div>
              {message !== undefined && (
                <p id={errorId} className="text-sm text-red-700">
                  {message}
                </p>
              )}
            </div>
          );
        })}
        <button type="button" onClick={() => setTypedRows([...rows, newRow()])} className={secondaryButton}>
          Add value
        </button>
      </fieldset>
      <div className="flex flex-wrap gap-2">
        <button type="submit" disabled={record.isPending} className={primaryButton}>
          {record.isPending ? "Saving…" : "Save analysis"}
        </button>
        <button type="button" onClick={onCancel} className={secondaryButton}>
          Cancel
        </button>
      </div>
    </form>
  );
}
