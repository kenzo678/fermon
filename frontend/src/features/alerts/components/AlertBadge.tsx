const MAX_SHOWN = 99;

/** Count pill for unresolved alerts; renders nothing when there are none. */
export function AlertBadge({ count }: { count: number }) {
  if (count <= 0) return null;
  return (
    <span className="inline-flex min-w-5 items-center justify-center gap-1 rounded-full bg-red-600 px-1.5 text-xs font-semibold tabular-nums text-white">
      {count > MAX_SHOWN ? `${MAX_SHOWN}+` : count}{" "}
      <span className="sr-only">{count === 1 ? "unresolved alert" : "unresolved alerts"}</span>
    </span>
  );
}
