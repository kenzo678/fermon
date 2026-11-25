import { useState } from "react";
import type { FormEvent } from "react";
import { fieldMessages } from "../../../shared/api";
import type { Role, User } from "../../../shared/api";
import { Field, controlClass } from "../../batches/components/Field";
import { isVersionConflict, useResetPassword, useUpdateUser } from "../hooks";
import { ROLES } from "../roles";

const buttonClass =
  "rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-500 disabled:opacity-60";

function ResetPasswordForm({ user, onDone }: { user: User; onDone: () => void }) {
  const reset = useResetPassword(user.id);
  const [password, setPassword] = useState("");
  const server = reset.error === null ? null : fieldMessages(reset.error);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    reset.mutate(password, { onSuccess: onDone });
  };
  return (
    <form onSubmit={submit} aria-label={`Reset password for ${user.display_name}`} className="space-y-2">
      {server !== null && server.general.length > 0 && (
        <p role="alert" className="text-sm text-red-800">
          {server.general.join(" ")}
        </p>
      )}
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
      <div className="flex gap-2">
        <button type="submit" disabled={reset.isPending} className={buttonClass}>
          Set temporary password
        </button>
        <button type="button" onClick={onDone} className={buttonClass}>
          Cancel
        </button>
      </div>
    </form>
  );
}

/** One user: role, state and the admin actions. Each action is its own mutation, so errors stay on the row. */
export function UserRow({
  user,
  isSelf,
  onReload,
}: {
  user: User;
  isSelf: boolean;
  onReload: () => void;
}) {
  const update = useUpdateUser(user.id);
  const [resetting, setResetting] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const failure = update.error === null ? null : fieldMessages(update.error);

  const edit = (changes: { role?: Role; active?: boolean }) => {
    setNotice(null);
    update.mutate({ version: user.version, ...changes });
  };

  return (
    <li
      aria-label={user.display_name}
      className="space-y-3 rounded-lg border border-slate-200 bg-white p-4 shadow-sm"
    >
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <div className="min-w-0 flex-1">
          <p className="font-medium">
            {user.display_name}
            {isSelf && <span className="ml-2 rounded-full bg-slate-100 px-2 py-0.5 text-xs">You</span>}
          </p>
          <p className="truncate text-sm text-slate-600">{user.email}</p>
          <p className="mt-1 flex flex-wrap gap-2 text-xs">
            {!user.active && <span className="rounded-full bg-slate-200 px-2 py-0.5">Inactive</span>}
            {user.must_change_password && (
              <span className="rounded-full bg-amber-100 px-2 py-0.5 text-amber-900">Must change password</span>
            )}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-2 text-sm">
            <span className="sr-only">Role</span>
            <select
              value={user.role}
              disabled={update.isPending}
              onChange={(e) => edit({ role: e.target.value as Role })}
              className={`${controlClass} w-auto`}
            >
              {ROLES.map(({ value, label }) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <button type="button" disabled={update.isPending} onClick={() => edit({ active: !user.active })} className={buttonClass}>
            {user.active ? "Deactivate" : "Activate"}
          </button>
          <button
            type="button"
            onClick={() => {
              setNotice(null);
              setResetting((open) => !open);
            }}
            className={buttonClass}
          >
            Reset password
          </button>
        </div>
      </div>
      {failure !== null && (
        <div role="alert" className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-900">
          {isVersionConflict(update.error) ? (
            <>
              <p>This user was changed by someone else. Reload the list to see the latest and try again.</p>
              <button type="button" onClick={onReload} className={`${buttonClass} mt-2`}>
                Reload users
              </button>
            </>
          ) : (
            [...Object.values(failure.fields), ...failure.general].map((message) => <p key={message}>{message}</p>)
          )}
        </div>
      )}
      {notice !== null && (
        <p role="status" className="rounded-md bg-emerald-50 p-3 text-sm text-emerald-900">
          {notice}
        </p>
      )}
      {resetting && (
        <ResetPasswordForm
          user={user}
          onDone={() => {
            setResetting(false);
            setNotice("Temporary password set. Their sessions were closed and they must change it at the next sign-in.");
          }}
        />
      )}
    </li>
  );
}
