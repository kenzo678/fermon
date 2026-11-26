import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import type { QualityParameterInfo, QualitySpec, QualityStage } from "../../../shared/api";
import { Field, controlClass } from "../../batches/components/Field";
import { STAGE_LABELS, STAGE_ORDER } from "../format";
import { SPEC_FIELD_ORDER, emptySpecValues, validateSpec, valuesFromSpec } from "../form";
import type { SpecErrors, SpecField, SpecServerErrors, SpecValues } from "../form";
import { primaryButton, secondaryButton } from "./buttons";

interface SpecFormProps {
  parameters: QualityParameterInfo[];
  /** Every spec of the profile: a stage offers only the parameters it does not specify yet. */
  specs: QualitySpec[];
  /** The spec being changed; stage and parameter stay fixed. `null` adds a new one. */
  editing: QualitySpec | null;
  submitting: boolean;
  /** Errors from the last failed request; field errors render next to their input. */
  serverErrors: SpecServerErrors | null;
  onSubmit: (values: SpecValues) => void;
  onCancel: () => void;
}

const RANGE_INPUTS: { name: SpecField; label: string }[] = [
  { name: "acceptance.min", label: "Acceptance min" },
  { name: "acceptance.max", label: "Acceptance max" },
  { name: "internal.min", label: "Internal min" },
  { name: "internal.max", label: "Internal max" },
  { name: "target", label: "Target" },
];

export function SpecForm({ parameters, specs, editing, submitting, serverErrors, onSubmit, onCancel }: SpecFormProps) {
  const [values, setValues] = useState<SpecValues>(() => (editing === null ? emptySpecValues() : valuesFromSpec(editing)));
  const [clientErrors, setClientErrors] = useState<SpecErrors>({});
  // Server messages the user already addressed by editing the input; they belong to one error set only.
  const [dismissal, setDismissal] = useState<{ source: SpecServerErrors | null; names: SpecField[] }>({
    source: serverErrors,
    names: [],
  });
  const formRef = useRef<HTMLFormElement>(null);
  const dismissed = dismissal.source === serverErrors ? dismissal.names : [];
  const visibleServerErrors: SpecErrors = { ...serverErrors?.fields };
  for (const name of dismissed) delete visibleServerErrors[name];
  const errors: SpecErrors = { ...visibleServerErrors, ...clientErrors };

  const focusFirstInvalid = (found: SpecErrors) => {
    const first = SPEC_FIELD_ORDER.find((name) => found[name] !== undefined);
    if (first !== undefined) (formRef.current?.elements.namedItem(first) as HTMLElement | null)?.focus();
  };
  // A rejected request names the offending inputs: move focus there like a client-side failure.
  useEffect(() => {
    if (serverErrors !== null) focusFirstInvalid(serverErrors.fields);
  }, [serverErrors]);

  const set = (changes: Partial<SpecValues>) => {
    setValues((current) => ({ ...current, ...changes }));
    const names = Object.keys(changes) as SpecField[];
    setClientErrors((current) => {
      const next = { ...current };
      for (const name of names) delete next[name];
      return next;
    });
    setDismissal((current) => ({
      source: serverErrors,
      names: [...(current.source === serverErrors ? current.names : []), ...names],
    }));
  };

  const taken = new Set(specs.filter((spec) => spec.stage === values.stage).map((spec) => spec.parameter));
  const available = editing === null ? parameters.filter((parameter) => !taken.has(parameter.code)) : parameters;
  const parameter = parameters.find((item) => item.code === values.parameter);

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    const found = validateSpec(values, parameter);
    setClientErrors(found);
    if (Object.keys(found).length > 0) {
      focusFirstInvalid(found);
      return;
    }
    onSubmit(values);
  };

  return (
    <form
      ref={formRef}
      onSubmit={handleSubmit}
      noValidate
      aria-label={editing === null ? "Add specification" : "Edit specification"}
      className="space-y-4 rounded-lg border border-slate-200 bg-white p-4 shadow-sm"
    >
      <h3 className="text-base font-semibold">
        {editing === null ? "New specification" : `Edit ${parameter?.name ?? editing.parameter}`}
      </h3>
      {serverErrors !== null && serverErrors.general.length > 0 && (
        <div role="alert" className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-900">
          {serverErrors.general.map((message) => (
            <p key={message}>{message}</p>
          ))}
        </div>
      )}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label="Stage" error={errors.stage}>
          <select
            name="stage"
            value={values.stage}
            disabled={editing !== null}
            onChange={(e) => {
              const stage = e.target.value as QualityStage | "";
              const stillFree = !specs.some((spec) => spec.stage === stage && spec.parameter === values.parameter);
              set({ stage, ...(stillFree ? {} : { parameter: "" }) });
            }}
            className={controlClass}
          >
            <option value="" disabled>
              Select a stage
            </option>
            {STAGE_ORDER.map((stage) => (
              <option key={stage} value={stage}>
                {STAGE_LABELS[stage]}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Parameter" error={errors.parameter}>
          <select
            name="parameter"
            value={values.parameter}
            disabled={editing !== null}
            onChange={(e) => set({ parameter: e.target.value })}
            className={controlClass}
          >
            <option value="" disabled>
              Select a parameter
            </option>
            {available.map((item) => (
              <option key={item.code} value={item.code}>
                {item.name} ({item.unit})
              </option>
            ))}
          </select>
        </Field>
      </div>
      {parameter !== undefined && (
        <p className="text-sm text-slate-600">
          Allowed values: {parameter.minimum} to {parameter.maximum} {parameter.unit}. Leave a side empty for no limit.
        </p>
      )}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {RANGE_INPUTS.map(({ name, label }) => (
          <Field key={name} label={label} error={errors[name]}>
            <input
              name={name}
              type="number"
              step="any"
              inputMode="decimal"
              value={values[name]}
              onChange={(e) => set({ [name]: e.target.value })}
              className={controlClass}
            />
          </Field>
        ))}
      </div>
      <div className="flex gap-2">
        <button type="submit" disabled={submitting} className={primaryButton}>
          {submitting ? "Saving…" : "Save specification"}
        </button>
        <button type="button" onClick={onCancel} className={secondaryButton}>
          Cancel
        </button>
      </div>
    </form>
  );
}
