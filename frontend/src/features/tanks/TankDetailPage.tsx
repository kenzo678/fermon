import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import {
  ConnectionIndicator,
  DEFAULT_RANGE,
  MeasurementChart,
  RangeSelector,
  parseRange,
  useAggregatedReadingsQuery,
  useLiveReadings,
} from "../readings";
import type { RangeValue } from "../readings";
import { ApiError } from "../../shared/api";
import { ActiveAlerts } from "../alerts/ActiveAlerts";
import { usePermissions } from "../auth";
import { formatPressureRange, formatTemperatureRange } from "../batches/format";
import { ErrorState } from "./components/ErrorState";
import { RenameTankForm } from "./components/RenameTankForm";
import { MEASUREMENTS, MEASUREMENT_ORDER, formatDateTime } from "./format";
import { useTankQuery } from "./useTankQuery";

const NO_TANKS: string[] = [];

const backLink = (
  <Link to="/" className="text-sm font-medium text-slate-700 underline">
    Back to tanks
  </Link>
);

export function TankDetailPage() {
  const { tankId = "" } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const range = parseRange(searchParams.get("range"));
  const tank = useTankQuery(tankId);
  const readings = useAggregatedReadingsQuery(tankId, range);
  const { canWriteBatches, canConfigureTanks } = usePermissions();
  const [renaming, setRenaming] = useState(false);
  // A terminal close (e.g. 4404) just reads "Offline"; the REST 404 path owns the missing tank.
  const liveStatus = useLiveReadings(tankId === "" ? NO_TANKS : [tankId]);

  const selectRange = (next: RangeValue) =>
    setSearchParams(
      (params) => {
        const updated = new URLSearchParams(params);
        if (next === DEFAULT_RANGE) updated.delete("range");
        else updated.set("range", next);
        return updated;
      },
      { replace: true },
    );

  if (tank.error instanceof ApiError && tank.error.status === 404) {
    return (
      <section className="space-y-2">
        <h2 className="text-xl font-semibold tracking-tight">Tank not found</h2>
        <p className="text-slate-600">There is no tank with id "{tankId}".</p>
        {backLink}
      </section>
    );
  }

  if (tank.data === undefined) {
    return tank.isPending ? (
      <div role="status" aria-label="Loading tank" className="h-16 animate-pulse rounded-lg bg-slate-200" />
    ) : (
      <ErrorState
        message={tank.error?.message ?? "Something went wrong"}
        onRetry={() => void tank.refetch()}
      />
    );
  }

  const series = readings.data?.series;
  const batch = tank.data.active_batch;
  const bands = {
    temperature: batch && { min: batch.targets.temperature_min, max: batch.targets.temperature_max },
    pressure: batch && { min: batch.targets.pressure_min, max: batch.targets.pressure_max },
    alcohol: null,
  };
  return (
    <section className="space-y-6">
      <header className="space-y-1">
        {backLink}
        <div className="flex items-center gap-3">
          <h2 className="text-xl font-semibold tracking-tight">
            {tank.data.display_name ?? tank.data.id}
          </h2>
          <ConnectionIndicator status={liveStatus} />
          {canConfigureTanks && !renaming && (
            <button type="button" onClick={() => setRenaming(true)} className="text-sm font-medium underline">
              Rename
            </button>
          )}
        </div>
        {canConfigureTanks && renaming && <RenameTankForm tank={tank.data} onDone={() => setRenaming(false)} />}
        <p className="text-sm text-slate-600">{tank.data.id}</p>
        <p className="text-sm text-slate-600">First seen {formatDateTime(tank.data.first_seen_at)}</p>
      </header>
      <section aria-label="Active batch" className="rounded-lg border border-slate-200 bg-white p-4">
        {batch ? (
          <>
            <p className="text-sm">
              <Link to={`/batches/${encodeURIComponent(batch.id)}`} className="font-semibold underline">
                {batch.beer_name}
              </Link>{" "}
              <span className="text-slate-600">· {batch.style}</span>
            </p>
            <dl className="mt-2 grid grid-cols-2 gap-2 text-sm">
              <div>
                <dt className="text-xs text-slate-500">Target temperature</dt>
                <dd className="font-medium tabular-nums">{formatTemperatureRange(batch.targets)}</dd>
              </div>
              <div>
                <dt className="text-xs text-slate-500">Target pressure</dt>
                <dd className="font-medium tabular-nums">{formatPressureRange(batch.targets)}</dd>
              </div>
            </dl>
          </>
        ) : (
          <p className="text-sm text-slate-600">
            No active batch.
            {canWriteBatches && (
              <>
                {" "}
                <Link to={`/batches/new?tank=${encodeURIComponent(tank.data.id)}`} className="font-medium underline">
                  Start a batch
                </Link>
              </>
            )}
          </p>
        )}
      </section>
      <ActiveAlerts tankId={tank.data.id} />
      <RangeSelector value={range} onChange={selectRange} />
      {series !== undefined ? (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 xl:grid-cols-1">
          {MEASUREMENT_ORDER.map((measurement) => (
            <MeasurementChart
              key={measurement}
              title={MEASUREMENTS[measurement].label}
              unit={MEASUREMENTS[measurement].unit}
              points={series[measurement] ?? []}
              target={bands[measurement] ?? undefined}
            />
          ))}
        </div>
      ) : readings.isPending ? (
        <div role="status" aria-label="Loading readings" className="h-64 animate-pulse rounded-lg bg-slate-200" />
      ) : (
        <ErrorState
          message={readings.error?.message ?? "Something went wrong"}
          onRetry={() => void readings.refetch()}
        />
      )}
    </section>
  );
}
