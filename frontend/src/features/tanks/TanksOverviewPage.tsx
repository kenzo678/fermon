import { useMemo } from "react";
// Deep imports on purpose: the readings barrel re-exports the ECharts-based charts, and pulling
// it into the overview would undo the lazy split of the detail route.
import { ConnectionIndicator } from "../readings/components/ConnectionIndicator";
import { useLiveReadings } from "../readings/useLiveReadings";
import { EmptyState } from "./components/EmptyState";
import { ErrorState } from "./components/ErrorState";
import { LoadingState } from "./components/LoadingState";
import { TankGrid } from "./components/TankGrid";
import { useTanksQuery } from "./useTanksQuery";

export function TanksOverviewPage() {
  const { data, error, isPending, refetch } = useTanksQuery();
  const liveStatus = useLiveReadings(useMemo(() => data?.map((tank) => tank.id) ?? [], [data]));

  // Cached data wins over a failed background refetch: keep the grid and flag the stale state.
  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-xl font-semibold tracking-tight">Tanks</h2>
        {data !== undefined && <ConnectionIndicator status={liveStatus} />}
      </div>
      {data !== undefined && error !== null && (
        <p
          role="status"
          aria-label="Refresh failed"
          className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-900"
        >
          Couldn't refresh: {error.message}. Showing the last known data.
        </p>
      )}
      {isPending ? (
        <LoadingState />
      ) : data !== undefined ? (
        data.length === 0 ? (
          <EmptyState />
        ) : (
          <TankGrid tanks={data} />
        )
      ) : (
        <ErrorState
          message={error?.message ?? "Something went wrong"}
          onRetry={() => void refetch()}
        />
      )}
    </section>
  );
}
