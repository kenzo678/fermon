import { useSearchParams } from "react-router";
import type { AlertKind, AlertStatus } from "../../shared/api";
import { ConnectionIndicator } from "../readings/components/ConnectionIndicator";
import { ErrorState } from "../tanks/components/ErrorState";
import { useTanksQuery } from "../tanks/useTanksQuery";
import { AcknowledgeableAlertList } from "./AcknowledgeableAlertList";
import type { AlertFilters } from "./api";
import { AlertFiltersBar } from "./components/AlertFiltersBar";
import { KIND_ORDER, STATUS_ORDER, UNRESOLVED } from "./format";
import { useAlertsQuery } from "./hooks";
import { useLiveAlertsStatus } from "./LiveAlerts";

function parseStatuses(values: string[]): AlertStatus[] {
  const picked = STATUS_ORDER.filter((status) => values.includes(status));
  return picked.length > 0 ? picked : UNRESOLVED;
}

const sameSet = (a: AlertStatus[], b: AlertStatus[]) => a.length === b.length && a.every((s) => b.includes(s));

export function AlertsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const statuses = parseStatuses(searchParams.getAll("status"));
  const tankId = searchParams.get("tank") ?? "";
  const kind = KIND_ORDER.find((k) => k === searchParams.get("kind")) ?? "";

  const filters: AlertFilters = { status: statuses };
  if (tankId !== "") filters.tank_id = tankId;
  if (kind !== "") filters.kind = kind;

  const alerts = useAlertsQuery(filters);
  const tanks = useTanksQuery();
  const liveStatus = useLiveAlertsStatus();

  const update = (change: (params: URLSearchParams) => void) =>
    setSearchParams(
      (params) => {
        const updated = new URLSearchParams(params);
        change(updated);
        return updated;
      },
      { replace: true },
    );

  const setOrDelete = (params: URLSearchParams, key: string, value: string) =>
    value === "" ? params.delete(key) : params.set(key, value);

  const toggleStatus = (status: AlertStatus) => {
    const next = statuses.includes(status) ? statuses.filter((s) => s !== status) : STATUS_ORDER.filter((s) => s === status || statuses.includes(s));
    // At least one status must stay selected; an empty filter would silently mean "unresolved".
    if (next.length === 0) return;
    update((params) => {
      params.delete("status");
      if (!sameSet(next, UNRESOLVED)) next.forEach((s) => params.append("status", s));
    });
  };

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-xl font-semibold tracking-tight">Alerts</h2>
        <ConnectionIndicator status={liveStatus} />
      </div>
      <AlertFiltersBar
        statuses={statuses}
        tankId={tankId}
        kind={kind}
        tanks={tanks.data ?? []}
        onToggleStatus={toggleStatus}
        onTankChange={(value) => update((params) => setOrDelete(params, "tank", value))}
        onKindChange={(value: AlertKind | "") => update((params) => setOrDelete(params, "kind", value))}
      />
      {alerts.data !== undefined ? (
        alerts.data.length === 0 ? (
          <p className="rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-600">
            No alerts match these filters
          </p>
        ) : (
          <AcknowledgeableAlertList alerts={alerts.data} />
        )
      ) : alerts.isPending ? (
        <div role="status" aria-label="Loading alerts" className="h-32 animate-pulse rounded-lg bg-slate-200" />
      ) : (
        <ErrorState message={alerts.error?.message ?? "Something went wrong"} onRetry={() => void alerts.refetch()} />
      )}
    </section>
  );
}
