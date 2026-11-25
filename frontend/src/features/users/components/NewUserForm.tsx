import { useState } from "react";
import type { FormEvent } from "react";
import { fieldMessages } from "../../../shared/api";
import type { Role } from "../../../shared/api";
import { Field, controlClass } from "../../batches/components/Field";
import { useCreateUser } from "../hooks";
import { ROLES } from "../roles";

export function NewUserForm({ onDone }: { onDone: () => void }) {
  const create = useCreateUser();
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [role, setRole] = useState<Role>("viewer");
  const [password, setPassword] = useState("");
  const server = create.error === null ? null : fieldMessages(create.error);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    create.mutate(
      { email: email.trim(), display_name: displayName.trim(), role, temporary_password: password },
      { onSuccess: onDone },
    );
  };

  return (
    <form
      onSubmit={submit}
      aria-label="New user"
      className="space-y-4 rounded-lg border border-slate-200 bg-white p-4 shadow-sm"
    >
      {server !== null && server.general.length > 0 && (
        <div role="alert" className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-900">
          {server.general.map((message) => (
            <p key={message}>{message}</p>
          ))}
        </div>
      )}
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Email" error={server?.fields.email}>
          <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className={controlClass} />
        </Field>
        <Field label="Display name" error={server?.fields.display_name}>
          <input required value={displayName} onChange={(e) => setDisplayName(e.target.value)} className={controlClass} />
        </Field>
        <Field label="Role" error={server?.fields.role}>
          <select value={role} onChange={(e) => setRole(e.target.value as Role)} className={controlClass}>
            {ROLES.map(({ value, label }) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Temporary password" error={server?.fields.temporary_password}>
          <input
            type="password"
            required
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className={controlClass}
          />
        </Field>
      </div>
      <p className="text-xs text-slate-600">
        At least 10 characters. The user must replace it the first time they sign in.
      </p>
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={create.isPending}
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-60"
        >
          Create user
        </button>
        <button
          type="button"
          onClick={onDone}
          className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium hover:bg-slate-50"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}
