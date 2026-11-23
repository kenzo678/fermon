import type { AlertStatus } from "../../../shared/api";
import { STATUS_LABELS } from "../format";

const STYLES: Record<AlertStatus, string> = {
  open: "bg-red-100 text-red-800",
  acknowledged: "bg-amber-100 text-amber-800",
  resolved: "bg-emerald-100 text-emerald-800",
};

export function AlertStatusChip({ status }: { status: AlertStatus }) {
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${STYLES[status]}`}>
      {STATUS_LABELS[status]}
    </span>
  );
}
