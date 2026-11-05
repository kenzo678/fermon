import type { LiveStatus } from "../useLiveReadings";

const PRESENTATION: Record<LiveStatus, { text: string; dot: string }> = {
  live: { text: "Live", dot: "bg-emerald-500" },
  reconnecting: { text: "Reconnecting…", dot: "bg-amber-500 animate-pulse" },
  offline: { text: "Offline", dot: "bg-slate-400" },
};

export function ConnectionIndicator({ status }: { status: LiveStatus }) {
  const { text, dot } = PRESENTATION[status];
  return (
    <span
      role="status"
      aria-label={`Connection: ${text}`}
      className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700"
    >
      <span aria-hidden="true" className={`h-2 w-2 rounded-full ${dot}`} />
      {text}
    </span>
  );
}
