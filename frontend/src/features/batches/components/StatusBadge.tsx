import type { BatchStatus } from "../../../shared/api";
import { STATUS_LABELS } from "../format";

const STYLES: Record<BatchStatus, string> = {
  planned: "bg-slate-100 text-slate-700",
  active: "bg-emerald-100 text-emerald-800",
  finished: "bg-sky-100 text-sky-800",
};

export function StatusBadge({ status }: { status: BatchStatus }) {
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${STYLES[status]}`}>
      {STATUS_LABELS[status]}
    </span>
  );
}
