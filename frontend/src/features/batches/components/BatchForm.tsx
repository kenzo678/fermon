import { Fragment, useEffect, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import type { BatchTemplate, BatchTemplateName, QualityProfile, Tank } from "../../../shared/api";
import { FIELD_ORDER, applyTemplate, validate } from "../form";
import type { FieldName, FormErrors, FormValues, ServerErrors } from "../form";
import { Field, controlClass } from "./Field";

interface BatchFormProps {
  mode: "create" | "edit";
  initialValues: FormValues;
  tanks: Tank[];
  templates: BatchTemplate[];
  /** The profiles the batch can be judged against; empty while loading or when there are none. */
  profiles?: QualityProfile[];
  submitLabel: string;
  submitting: boolean;
  /** Errors from the last failed request; field errors render next to their input. */
  serverErrors: ServerErrors | null;
  readOnly?: boolean;
  /** Rendered inside the general error alert (e.g. a reload button for a stale edit). */
  errorAction?: ReactNode;
  /** Reports whether the inputs differ from `initialValues`. */
  onDirtyChange?: (dirty: boolean) => void;
  onSubmit: (values: FormValues) => void;
}

const TEMPLATE_LABELS: Record<BatchTemplateName, string> = { ale: "Ale", lager: "Lager", custom: "Custom" };
const TEMPLATE_OPTIONS: BatchTemplateName[] = ["ale", "lager", "custom"];

const TARGET_INPUTS: { name: FieldName; label: string }[] = [
  { name: "temperature_min", label: "Minimum temperature (°C)" },
  { name: "temperature_max", label: "Maximum temperature (°C)" },
  { name: "pressure_min", label: "Minimum pressure (bar)" },
  { name: "pressure_max", label: "Maximum pressure (bar)" },
  { name: "expected_final_abv", label: "Expected final ABV (%)" },
];

/** Controlled, presentational form shared by create and edit. */
export function BatchForm({
  mode,
  initialValues,
  tanks,
  templates,
  profiles = [],
  submitLabel,
  submitting,
  serverErrors,
  readOnly = false,
  errorAction,
  onDirtyChange,
  onSubmit,
}: BatchFormProps) {
  const [values, setValues] = useState(initialValues);
  const [baseline, setBaseline] = useState(initialValues);
  const [clientErrors, setClientErrors] = useState<FormErrors>({});
  // Server errors the user already addressed by editing the field; they belong to one error set only.
  const [dismissal, setDismissal] = useState<{ source: ServerErrors | null; names: FieldName[] }>({
    source: serverErrors,
    names: [],
  });
  const formRef = useRef<HTMLFormElement>(null);
  const dismissed = dismissal.source === serverErrors ? dismissal.names : [];
  const visibleServerErrors: FormErrors = { ...serverErrors?.fields };
  for (const name of dismissed) delete visibleServerErrors[name];
  const errors: FormErrors = { ...visibleServerErrors, ...clientErrors };

  // The parent hands over a new server copy by passing a new `initialValues`: restart from it.
  if (baseline !== initialValues) {
    setBaseline(initialValues);
    setValues(initialValues);
    setClientErrors({});
  }
  const dirty = FIELD_ORDER.some((name) => values[name] !== baseline[name]);
  useEffect(() => {
    onDirtyChange?.(dirty);
  }, [dirty, onDirtyChange]);

  const clearErrors = (names: FieldName[]) => {
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

  const focusFirstInvalid = (found: FormErrors) => {
    const first = FIELD_ORDER.find((name) => found[name] !== undefined);
    if (first !== undefined) (formRef.current?.elements.namedItem(first) as HTMLElement | null)?.focus();
  };

  // A rejected request names the offending inputs: move focus there like a client-side failure.
  useEffect(() => {
    if (serverErrors !== null) focusFirstInvalid(serverErrors.fields);
  }, [serverErrors]);

  const set = (name: FieldName, value: string) => {
    setValues((current) => ({ ...current, [name]: value }));
    clearErrors([name]);
  };

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    const found = validate(values);
    setClientErrors(found);
    if (Object.keys(found).length > 0) {
      focusFirstInvalid(found);
      return;
    }
    onSubmit(values);
  };

  const text = (name: FieldName, label: string, type = "text", className?: string) => (
    <Field label={label} error={errors[name]} className={className}>
      <input
        name={name}
        type={type}
        value={values[name]}
        onChange={(e) => set(name, e.target.value)}
        className={controlClass}
        {...(type === "number" ? { step: "any", inputMode: "decimal" as const } : {})}
      />
    </Field>
  );

  return (
    <form ref={formRef} onSubmit={handleSubmit} noValidate className="space-y-6">
      {serverErrors !== null && serverErrors.general.length > 0 && (
        <div role="alert" className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-900">
          {serverErrors.general.map((message) => (
            <p key={message}>{message}</p>
          ))}
          {errorAction}
        </div>
      )}
      <fieldset disabled={readOnly} className="space-y-6">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Tank" error={errors.tank_id}>
            <select
              name="tank_id"
              value={values.tank_id}
              disabled={mode === "edit"}
              onChange={(e) => set("tank_id", e.target.value)}
              className={controlClass}
            >
              <option value="">Select a tank</option>
              {tanks.map((tank) => (
                <option key={tank.id} value={tank.id}>
                  {tank.display_name ?? tank.id}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Template" error={errors.template}>
            <select
              name="template"
              value={values.template}
              onChange={(e) => {
                setValues((current) => applyTemplate(current, e.target.value as BatchTemplateName, templates));
                clearErrors(["template", ...TARGET_INPUTS.map(({ name }) => name)]);
              }}
              className={controlClass}
            >
              <option value="" disabled>
                Select a template
              </option>
              {TEMPLATE_OPTIONS.map((template) => (
                <option key={template} value={template}>
                  {TEMPLATE_LABELS[template]}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Quality profile" error={errors.quality_profile_id}>
            <select
              name="quality_profile_id"
              value={values.quality_profile_id}
              onChange={(e) => set("quality_profile_id", e.target.value)}
              className={controlClass}
            >
              <option value="">None</option>
              {profiles.map((profile) => (
                <option key={profile.id} value={profile.id}>
                  {profile.name}
                </option>
              ))}
            </select>
          </Field>
          {text("beer_name", "Beer name")}
          {text("style", "Style")}
          {text("planned_start", "Planned start", "datetime-local")}
          {text("expected_end", "Expected end", "datetime-local")}
        </div>
        <fieldset className="space-y-3">
          <legend className="text-sm font-semibold text-slate-900">Target ranges</legend>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {TARGET_INPUTS.map(({ name, label }) => (
              <Fragment key={name}>{text(name, label, "number")}</Fragment>
            ))}
          </div>
        </fieldset>
        <Field label="Notes" error={errors.notes}>
          <textarea
            name="notes"
            rows={3}
            value={values.notes}
            onChange={(e) => set("notes", e.target.value)}
            className={controlClass}
          />
        </Field>
      </fieldset>
      {!readOnly && (
        <button
          type="submit"
          disabled={submitting}
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-500 focus-visible:ring-offset-2 disabled:opacity-60"
        >
          {submitting ? "Saving…" : submitLabel}
        </button>
      )}
    </form>
  );
}
