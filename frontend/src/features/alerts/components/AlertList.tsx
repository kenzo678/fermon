import type { Alert } from "../../../shared/api";
import { AlertItem } from "./AlertItem";

interface AlertListProps {
  alerts: Alert[];
  onAcknowledge?: (alert: Alert) => void;
  /** The alert whose acknowledgement is in flight. */
  acknowledgingId?: string | null;
  /** The failed acknowledgement, shown on its alert. */
  error?: { id: string; message: string } | null;
  showTank?: boolean;
}

export function AlertList({ alerts, onAcknowledge, acknowledgingId, error, showTank }: AlertListProps) {
  return (
    <ul aria-label="Alerts" className="space-y-3">
      {alerts.map((alert) => (
        <li key={alert.id}>
          <AlertItem
            alert={alert}
            onAcknowledge={onAcknowledge}
            acknowledging={acknowledgingId === alert.id}
            error={error?.id === alert.id ? error.message : null}
            showTank={showTank}
          />
        </li>
      ))}
    </ul>
  );
}
