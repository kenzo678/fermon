import { useState } from "react";
import type { FormEvent } from "react";
import type { FieldMessages, QualityProfileTemplate } from "../../../shared/api";
import { Field, controlClass } from "../../batches/components/Field";
import { templateLabel } from "../format";
import { primaryButton, secondaryButton } from "./buttons";

interface NewProfileFormProps {
  templates: QualityProfileTemplate[];
  submitting: boolean;
  /** Errors from the last failed request; a 409 on `name` renders next to the input. */
  serverErrors: FieldMessages | null;
  onSubmit: (body: { name: string; template?: string }) => void;
  onCancel: () => void;
}

export function NewProfileForm({ templates, submitting, serverErrors, onSubmit, onCancel }: NewProfileFormProps) {
  const [name, setName] = useState("");
  const [template, setTemplate] = useState("");
  const [clientError, setClientError] = useState<string>();
  // Editing the name answers the server's complaint about it: remember which error set was addressed.
  const [addressed, setAddressed] = useState<FieldMessages | null>(null);
  const nameError = clientError ?? (addressed === serverErrors ? undefined : serverErrors?.fields.name);
  const general = serverErrors === null ? [] : [...serverErrors.general, ...Object.entries(serverErrors.fields).filter(([field]) => field !== "name").map(([, message]) => message)];

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (name.trim() === "") {
      setClientError("Enter a name");
      return;
    }
    onSubmit(template === "" ? { name: name.trim() } : { name: name.trim(), template });
  };

  return (
    <form onSubmit={handleSubmit} noValidate className="space-y-4 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <h3 className="text-base font-semibold">New profile</h3>
      {general.length > 0 && (
        <div role="alert" className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-900">
          {general.map((message) => (
            <p key={message}>{message}</p>
          ))}
        </div>
      )}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label="Name" error={nameError}>
          <input
            name="name"
            value={name}
            onChange={(e) => {
              setName(e.target.value);
              setClientError(undefined);
              setAddressed(serverErrors);
            }}
            className={controlClass}
          />
        </Field>
        <Field label="Template">
          <select name="template" value={template} onChange={(e) => setTemplate(e.target.value)} className={controlClass}>
            <option value="">Blank profile</option>
            {templates.map((item) => (
              <option key={item.template} value={item.template}>
                {templateLabel(item.template)}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <div className="flex gap-2">
        <button type="submit" disabled={submitting} className={primaryButton}>
          {submitting ? "Creating…" : "Create profile"}
        </button>
        <button type="button" onClick={onCancel} className={secondaryButton}>
          Cancel
        </button>
      </div>
    </form>
  );
}
