import { useState } from "react";
import type { FormEvent } from "react";
import { fieldMessages } from "../../../shared/api";
import type { Tank } from "../../../shared/api";
import { Field, controlClass } from "../../batches/components/Field";
import { primaryButton, secondaryButton } from "../../quality/components/buttons";
import { useRenameTank } from "../useRenameTank";

const MAX_LENGTH = 64;

interface RenameTankFormProps {
  tank: Tank;
  /** Called after a successful save or clear, and on Cancel. */
  onDone: () => void;
}

export function RenameTankForm({ tank, onDone }: RenameTankFormProps) {
  const rename = useRenameTank(tank.id);
  const [name, setName] = useState(tank.display_name ?? "");
  const [clientError, setClientError] = useState<string>();
  const server = rename.error === null ? null : fieldMessages(rename.error);
  const fieldError = clientError ?? server?.fields.display_name;
  const general = server === null ? [] : [...server.general];

  const save = (displayName: string | null) => rename.mutate(displayName, { onSuccess: onDone });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const trimmed = name.trim();
    if (trimmed === "") return setClientError("Enter a name, or use Clear name");
    if (trimmed.length > MAX_LENGTH) return setClientError(`Use at most ${MAX_LENGTH} characters`);
    save(trimmed);
  };

  return (
    <form onSubmit={submit} noValidate aria-label="Rename tank" className="max-w-md space-y-3">
      {general.length > 0 && (
        <div role="alert" className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-900">
          {general.map((message) => (
            <p key={message}>{message}</p>
          ))}
        </div>
      )}
      <Field label="Display name" error={fieldError}>
        <input
          type="text"
          value={name}
          onChange={(event) => {
            setName(event.target.value);
            setClientError(undefined);
            rename.reset();
          }}
          className={controlClass}
        />
      </Field>
      <div className="flex flex-wrap gap-2">
        <button type="submit" disabled={rename.isPending} className={primaryButton}>
          {rename.isPending ? "Saving…" : "Save"}
        </button>
        {tank.display_name !== null && (
          <button type="button" disabled={rename.isPending} onClick={() => save(null)} className={secondaryButton}>
            Clear name
          </button>
        )}
        <button type="button" onClick={onDone} className={secondaryButton}>
          Cancel
        </button>
      </div>
    </form>
  );
}
