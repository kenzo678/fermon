import { Link } from "react-router";
import type { Alert } from "../../../shared/api";
import { formatDateTime } from "../../tanks/format";
import { KIND_LABELS, alertMessage, resolutionNote } from "../format";
import { AlertStatusChip } from "./AlertStatusChip";

interface AlertItemProps {
  alert: Alert;
  /** Omit to render a read-only item. */
  onAcknowledge?: (alert: Alert) => void;
  acknowledging?: boolean;
  error?: string | null;
  showTank?: boolean;
}

function Stamp({ label, iso }: { label: string; iso: string }) {
  return (
    <span>
      {label} <time dateTime={iso}>{formatDateTime(iso)}</time>
    </span>
  );
}

export function AlertItem({ alert, onAcknowledge, acknowledging = false, error, showTank = true }: AlertItemProps) {
  const note = resolutionNote(alert);
  return (
    <article data-alert-id={alert.id} className="space-y-2 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-center gap-2">
        <AlertStatusChip status={alert.status} />
        <span className="text-xs text-slate-500">{KIND_LABELS[alert.kind]}</span>
        {showTank && (
          <Link to={`/tanks/${encodeURIComponent(alert.tank_id)}`} className="text-sm font-medium underline">
            {alert.tank_id}
          </Link>
        )}
      </div>
      <p className="text-sm font-medium">{alertMessage(alert)}</p>
      {note !== null && <p className="text-sm text-slate-600">{note}</p>}
      <p className="flex flex-wrap gap-x-4 text-xs text-slate-500">
        <Stamp label="Opened" iso={alert.opened_at} />
        {alert.acknowledged_at !== null && <Stamp label="Acknowledged" iso={alert.acknowledged_at} />}
        {alert.resolved_at !== null && <Stamp label="Resolved" iso={alert.resolved_at} />}
      </p>
      {error != null && (
        <p role="alert" className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-900">
          {error}
        </p>
      )}
      {alert.status === "open" && onAcknowledge !== undefined && (
        <button
          type="button"
          disabled={acknowledging}
          onClick={() => onAcknowledge(alert)}
          className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-500 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {acknowledging ? "Acknowledging…" : "Acknowledge"}
        </button>
      )}
    </article>
  );
}
