import { Link } from "react-router";
import type { Tank } from "../../../shared/api";
import { AlertBadge } from "../../alerts/components/AlertBadge";
import {
  formatDateTime,
  formatReading,
  MEASUREMENT_ORDER,
  MEASUREMENTS,
  newestTimestamp,
} from "../format";

interface TankCardProps {
  tank: Tank;
}

function Timestamp({ iso }: { iso: string }) {
  return <time dateTime={iso}>{formatDateTime(iso)}</time>;
}

export function TankCard({ tank }: TankCardProps) {
  const updatedAt = newestTimestamp(MEASUREMENT_ORDER.map((m) => tank.latest[m]));
  return (
    <article className="relative flex h-full flex-col gap-4 rounded-lg border border-slate-200 bg-white p-4 shadow-sm transition-shadow focus-within:ring-2 focus-within:ring-slate-400 hover:shadow-md">
      <h3 className="text-base font-semibold">
        {/* The pseudo-element stretches the link over the whole card. */}
        <Link
          to={`/tanks/${encodeURIComponent(tank.id)}`}
          className="after:absolute after:inset-0 focus:outline-none"
        >
          {tank.display_name ?? tank.id}
        </Link>
      </h3>
      {tank.active_batch ? (
        <p className="text-sm text-slate-700">
          {/* Above the stretched card link so the batch stays clickable. */}
          <Link
            to={`/batches/${encodeURIComponent(tank.active_batch.id)}`}
            className="relative z-10 font-medium underline"
          >
            {tank.active_batch.beer_name}
          </Link>{" "}
          <span className="text-slate-500">{tank.active_batch.style}</span>
        </p>
      ) : (
        <p className="text-sm text-slate-500">No active batch</p>
      )}
      {tank.open_alerts > 0 && (
        <p className="text-sm">
          {/* Above the stretched card link so the alerts of this tank stay one click away. */}
          <Link
            to={`/alerts?tank=${encodeURIComponent(tank.id)}`}
            className="relative z-10 inline-flex items-center gap-1.5 font-medium text-red-800 underline"
          >
            <AlertBadge count={tank.open_alerts} />
            <span aria-hidden="true">{tank.open_alerts === 1 ? "alert" : "alerts"}</span>
          </Link>
        </p>
      )}
      <dl className="grid grid-cols-3 gap-2">
        {MEASUREMENT_ORDER.map((measurement) => (
          <div key={measurement}>
            <dt className="text-xs text-slate-500">{MEASUREMENTS[measurement].label}</dt>
            <dd className="text-sm font-medium tabular-nums">
              {formatReading(measurement, tank.latest[measurement])}
            </dd>
          </div>
        ))}
      </dl>
      <div className="mt-auto space-y-0.5 text-xs text-slate-500">
        {updatedAt ? (
          <p>
            Updated <Timestamp iso={updatedAt} />
          </p>
        ) : (
          <p>No readings yet</p>
        )}
        <p>
          First seen <Timestamp iso={tank.first_seen_at} />
        </p>
      </div>
    </article>
  );
}
