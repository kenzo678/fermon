import { Link, useParams, useSearchParams } from "react-router";
import {
  DEFAULT_RANGE,
  MeasurementChart,
  RangeSelector,
  parseRange,
  useAggregatedReadingsQuery,
} from "../readings";
import type { RangeValue } from "../readings";
import { ApiError } from "../../shared/api";
import { ErrorState } from "./components/ErrorState";
import { MEASUREMENTS, MEASUREMENT_ORDER, formatDateTime } from "./format";
import { useTankQuery } from "./useTankQuery";

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
  return (
    <section className="space-y-6">
      <header className="space-y-1">
        {backLink}
        <h2 className="text-xl font-semibold tracking-tight">
          {tank.data.display_name ?? tank.data.id}
        </h2>
        <p className="text-sm text-slate-600">{tank.data.id}</p>
        <p className="text-sm text-slate-600">First seen {formatDateTime(tank.data.first_seen_at)}</p>
      </header>
      <RangeSelector value={range} onChange={selectRange} />
      {series !== undefined ? (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 xl:grid-cols-1">
          {MEASUREMENT_ORDER.map((measurement) => (
            <MeasurementChart
              key={measurement}
              title={MEASUREMENTS[measurement].label}
              unit={MEASUREMENTS[measurement].unit}
              points={series[measurement] ?? []}
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
