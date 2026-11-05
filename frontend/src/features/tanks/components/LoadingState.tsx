const PLACEHOLDERS = [0, 1, 2];

export function LoadingState() {
  return (
    <div
      role="status"
      aria-label="Loading tanks"
      aria-busy="true"
      className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"
    >
      {PLACEHOLDERS.map((key) => (
        <div
          key={key}
          data-skeleton
          aria-hidden="true"
          className="h-36 animate-pulse rounded-lg bg-slate-200"
        />
      ))}
    </div>
  );
}
