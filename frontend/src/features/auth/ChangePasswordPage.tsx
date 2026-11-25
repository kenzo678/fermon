import { useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router";
import { fieldMessages } from "../../shared/api";
import { Field, controlClass } from "../batches/components/Field";
import { useChangePassword, useSession } from "./hooks";
import { submitClass } from "./LoginPage";

/** Same minimum as the API (`WeakPasswordError`); the server stays the authority. */
export const MIN_PASSWORD_LENGTH = 10;

export function ChangePasswordPage() {
  const navigate = useNavigate();
  const session = useSession();
  const change = useChangePassword();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const forced = session.data?.must_change_password === true;
  const server = change.error === null ? null : fieldMessages(change.error);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const found: Record<string, string> = {};
    if (current === "") found.current_password = "Enter your current password.";
    if (next.length < MIN_PASSWORD_LENGTH) found.new_password = `Use at least ${MIN_PASSWORD_LENGTH} characters.`;
    else if (confirm !== next) found.confirm = "The passwords do not match.";
    setErrors(found);
    if (Object.keys(found).length > 0) return;
    change.mutate(
      { current_password: current, new_password: next },
      { onSuccess: () => void navigate("/", { replace: true }) },
    );
  };

  return (
    <section className="mx-auto max-w-md space-y-4">
      <h2 className="text-xl font-semibold tracking-tight">Change password</h2>
      {forced && (
        <p role="status" className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          You are using a temporary password. Choose a new one to continue.
        </p>
      )}
      <form onSubmit={submit} noValidate className="space-y-4 rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
        {server !== null && server.general.length > 0 && (
          <div role="alert" className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-900">
            {server.general.map((message) => (
              <p key={message}>{message}</p>
            ))}
          </div>
        )}
        <Field label="Current password" error={errors.current_password ?? server?.fields.current_password}>
          <input
            type="password"
            autoComplete="current-password"
            value={current}
            onChange={(event) => setCurrent(event.target.value)}
            className={controlClass}
          />
        </Field>
        <Field label="New password" error={errors.new_password ?? server?.fields.new_password}>
          <input
            type="password"
            autoComplete="new-password"
            value={next}
            onChange={(event) => setNext(event.target.value)}
            className={controlClass}
          />
        </Field>
        <Field label="Confirm new password" error={errors.confirm}>
          <input
            type="password"
            autoComplete="new-password"
            value={confirm}
            onChange={(event) => setConfirm(event.target.value)}
            className={controlClass}
          />
        </Field>
        <button type="submit" disabled={change.isPending} className={submitClass}>
          {change.isPending ? "Saving…" : "Change password"}
        </button>
      </form>
    </section>
  );
}
