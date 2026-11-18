import type { Alert } from "../../shared/api";
import { AlertList } from "./components/AlertList";
import { acknowledgeErrorMessage, useAcknowledgeAlert } from "./hooks";

/** Container: an alert list wired to the acknowledge mutation (pending and error per alert). */
export function AcknowledgeableAlertList({ alerts, showTank }: { alerts: Alert[]; showTank?: boolean }) {
  const acknowledge = useAcknowledgeAlert();
  const message = acknowledgeErrorMessage(acknowledge.error);
  return (
    <AlertList
      alerts={alerts}
      showTank={showTank}
      onAcknowledge={(alert) => acknowledge.mutate(alert)}
      acknowledgingId={acknowledge.isPending ? acknowledge.variables.id : null}
      error={message !== null && acknowledge.variables ? { id: acknowledge.variables.id, message } : null}
    />
  );
}
