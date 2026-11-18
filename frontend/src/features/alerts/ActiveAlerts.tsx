import { ErrorState } from "../tanks/components/ErrorState";
import { AcknowledgeableAlertList } from "./AcknowledgeableAlertList";
import { useAlertsQuery } from "./hooks";

/** The unresolved alerts of one tank, for its detail page. */
export function ActiveAlerts({ tankId }: { tankId: string }) {
  const alerts = useAlertsQuery({ tank_id: tankId });
  return (
    <section aria-labelledby="active-alerts-heading" className="space-y-3">
      <h3 id="active-alerts-heading" className="text-base font-semibold">
        Active alerts
      </h3>
      {alerts.data !== undefined ? (
        alerts.data.length === 0 ? (
          <p className="text-sm text-slate-600">No active alerts</p>
        ) : (
          <AcknowledgeableAlertList alerts={alerts.data} showTank={false} />
        )
      ) : alerts.isPending ? (
        <div role="status" aria-label="Loading alerts" className="h-16 animate-pulse rounded-lg bg-slate-200" />
      ) : (
        <ErrorState message={alerts.error?.message ?? "Something went wrong"} onRetry={() => void alerts.refetch()} />
      )}
    </section>
  );
}
