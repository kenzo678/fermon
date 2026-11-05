import { Link } from "react-router";
import type { Tank } from "../../../shared/api";
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
