import type { Alert } from "../../shared/api";
import { usePermissions } from "../auth";
import { AlertList } from "./components/AlertList";
import { acknowledgeErrorMessage, useAcknowledgeAlert } from "./hooks";

/** Container: an alert list wired to the acknowledge mutation (pending and error per alert). */
export function AcknowledgeableAlertList({ alerts, showTank }: { alerts: Alert[]; showTank?: boolean }) {
  const acknowledge = useAcknowledgeAlert();
  const { canAcknowledgeAlerts } = usePermissions();
  const message = acknowledgeErrorMessage(acknowledge.error);
  return (
    <AlertList
      alerts={alerts}
      showTank={showTank}
      // Omitting the handler renders the list read-only.
      onAcknowledge={canAcknowledgeAlerts ? (alert) => acknowledge.mutate(alert) : undefined}
      acknowledgingId={acknowledge.isPending ? acknowledge.variables.id : null}
      error={message !== null && acknowledge.variables ? { id: acknowledge.variables.id, message } : null}
    />
  );
}
