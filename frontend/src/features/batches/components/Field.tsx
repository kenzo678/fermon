import type { ReactElement } from "react";
import { cloneElement, useId } from "react";

interface FieldProps {
  label: string;
  error?: string;
  /** The single control; Field wires its id, aria-invalid and aria-describedby. */
  children: ReactElement<Record<string, unknown>>;
  className?: string;
}

export const controlClass =
  "block w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-500 disabled:bg-slate-100 disabled:text-slate-600 aria-[invalid=true]:border-red-600";

export function Field({ label, error, children, className }: FieldProps) {
  const id = useId();
  const errorId = `${id}-error`;
  return (
    <div className={className}>
      <label htmlFor={id} className="mb-1 block text-sm font-medium text-slate-800">
        {label}
      </label>
      {cloneElement(children, {
        id,
        "aria-invalid": error ? true : undefined,
        "aria-describedby": error ? errorId : undefined,
      })}
      {error && (
        <p id={errorId} className="mt-1 text-sm text-red-700">
          {error}
        </p>
      )}
    </div>
  );
}
