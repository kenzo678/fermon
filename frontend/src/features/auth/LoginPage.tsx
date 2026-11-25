import { useState } from "react";
import type { FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router";
import { ApiError } from "../../shared/api";
import { Field, controlClass } from "../batches/components/Field";
import { useLogin, useSession } from "./hooks";

/** "in 15 minutes" for a `Retry-After` of 900 s; rounds up so the user never retries too early. */
export function formatRetryDelay(seconds: number | undefined): string {
  if (seconds === undefined) return "later";
  if (seconds < 60) return `in ${seconds} ${seconds === 1 ? "second" : "seconds"}`;
  const minutes = Math.ceil(seconds / 60);
  return `in ${minutes} ${minutes === 1 ? "minute" : "minutes"}`;
}

function loginErrorMessage(error: Error): string {
  if (error instanceof ApiError && error.status === 401) return "Incorrect email or password.";
  if (error instanceof ApiError && error.status === 429) {
    return `Too many failed attempts. Try again ${formatRetryDelay(error.retryAfterSeconds)}.`;
  }
  return error.message;
}

/** Only in-app paths are honoured as a return target: never a URL that could leave the site. */
export function returnTarget(state: unknown): string {
  const from = (state as { from?: unknown } | null)?.from;
  return typeof from === "string" && from.startsWith("/") && !from.startsWith("//") ? from : "/";
}

export const submitClass =
  "w-full rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-500 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60";

export function LoginPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const session = useSession();
  const login = useLogin();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<{ email?: string; password?: string }>({});
  const target = returnTarget(location.state);

  if (session.data) return <Navigate to={target} replace />;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const next = {
      ...(email.trim() === "" && { email: "Enter your email." }),
      ...(password === "" && { password: "Enter your password." }),
    };
    setErrors(next);
    if (Object.keys(next).length > 0) return;
    login.mutate(
      { email: email.trim(), password },
      { onSuccess: () => void navigate(target, { replace: true }) },
    );
  };

  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center gap-6 px-4">
      <h1 className="text-center text-2xl font-semibold tracking-tight">Fermon</h1>
      <form onSubmit={submit} noValidate className="space-y-4 rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-lg font-semibold tracking-tight">Sign in</h2>
        {login.error !== null && (
          <p role="alert" className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-900">
            {loginErrorMessage(login.error)}
          </p>
        )}
        <Field label="Email" error={errors.email}>
          <input
            type="email"
            autoComplete="username"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            className={controlClass}
          />
        </Field>
        <Field label="Password" error={errors.password}>
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className={controlClass}
          />
        </Field>
        <button type="submit" disabled={login.isPending} className={submitClass}>
          {login.isPending ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </main>
  );
}
