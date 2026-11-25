import { Link, useSearchParams } from "react-router";
import type { Batch, BatchStatus } from "../../shared/api";
import { formatDateTime } from "../tanks/format";
import { ErrorState } from "../tanks/components/ErrorState";
import { useTanksQuery } from "../tanks/useTanksQuery";
import { controlClass } from "./components/Field";
import { StatusBadge } from "./components/StatusBadge";
import { STATUS_LABELS, STATUS_ORDER, formatTemperatureRange } from "./format";
import { useBatchesQuery } from "./hooks";
import type { BatchFilters } from "./api";
import { usePermissions } from "../auth";

function parseStatus(value: string | null): BatchStatus | undefined {
  return STATUS_ORDER.find((status) => status === value);
}

const linkClass = "font-medium underline";

function BatchTable({ batches }: { batches: Batch[] }) {
  return (
    <table className="hidden w-full text-left text-sm md:table">
      <caption className="sr-only">Batches</caption>
      <thead className="border-b border-slate-200 text-xs uppercase text-slate-500">
        <tr>
          {["Beer", "Tank", "Style", "Status", "Temperature", "Planned start"].map((heading) => (
            <th key={heading} scope="col" className="px-3 py-2 font-medium">
              {heading}
            </th>
          ))}
        </tr>
      </thead>
      <tbody className="divide-y divide-slate-100 bg-white">
        {batches.map((batch) => (
          <tr key={batch.id}>
            <th scope="row" className="px-3 py-2 font-medium">
              <Link to={`/batches/${encodeURIComponent(batch.id)}`} className={linkClass}>
                {batch.beer_name}
              </Link>
            </th>
            <td className="px-3 py-2">{batch.tank_id}</td>
            <td className="px-3 py-2">{batch.style}</td>
            <td className="px-3 py-2">
              <StatusBadge status={batch.status} />
            </td>
            <td className="px-3 py-2 tabular-nums">{formatTemperatureRange(batch.targets)}</td>
            <td className="px-3 py-2">{formatDateTime(batch.planned_start)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function BatchCards({ batches }: { batches: Batch[] }) {
  return (
    <ul className="space-y-3 md:hidden">
      {batches.map((batch) => (
        <li key={batch.id} className="space-y-1 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex items-center justify-between gap-2">
            <Link to={`/batches/${encodeURIComponent(batch.id)}`} className={linkClass}>
              {batch.beer_name}
            </Link>
            <StatusBadge status={batch.status} />
          </div>
          <p className="text-sm text-slate-600">
            {batch.style} · {batch.tank_id}
          </p>
          <p className="text-sm tabular-nums text-slate-600">{formatTemperatureRange(batch.targets)}</p>
        </li>
      ))}
    </ul>
  );
}

export function BatchesPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const filters: BatchFilters = {};
  const tankId = searchParams.get("tank_id");
  const status = parseStatus(searchParams.get("status"));
  if (tankId) filters.tank_id = tankId;
  if (status) filters.status = status;

  const batches = useBatchesQuery(filters);
  const tanks = useTanksQuery();
  const { canWriteBatches } = usePermissions();

  const setFilter = (key: "tank_id" | "status", value: string) =>
    setSearchParams(
      (params) => {
        const updated = new URLSearchParams(params);
        if (value === "") updated.delete(key);
        else updated.set(key, value);
        return updated;
      },
      { replace: true },
    );

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-xl font-semibold tracking-tight">Batches</h2>
        {canWriteBatches && (
          <Link
            to="/batches/new"
            className="rounded-md bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-500 focus-visible:ring-offset-2"
          >
            New batch
          </Link>
        )}
      </div>
      <div className="flex flex-wrap gap-4">
        <div>
          <label htmlFor="filter-tank" className="mb-1 block text-sm font-medium">
            Tank
          </label>
          <select
            id="filter-tank"
            value={tankId ?? ""}
            onChange={(e) => setFilter("tank_id", e.target.value)}
            className={controlClass}
          >
            <option value="">All tanks</option>
            {tanks.data?.map((tank) => (
              <option key={tank.id} value={tank.id}>
                {tank.display_name ?? tank.id}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="filter-status" className="mb-1 block text-sm font-medium">
            Status
          </label>
          <select
            id="filter-status"
            value={status ?? ""}
            onChange={(e) => setFilter("status", e.target.value)}
            className={controlClass}
          >
            <option value="">All statuses</option>
            {STATUS_ORDER.map((value) => (
              <option key={value} value={value}>
                {STATUS_LABELS[value]}
              </option>
            ))}
          </select>
        </div>
      </div>
      {batches.data !== undefined ? (
        batches.data.length === 0 ? (
          <p className="rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-600">
            No batches match these filters
          </p>
        ) : (
          <>
            <BatchTable batches={batches.data} />
            <BatchCards batches={batches.data} />
          </>
        )
      ) : batches.isPending ? (
        <div role="status" aria-label="Loading batches" className="h-32 animate-pulse rounded-lg bg-slate-200" />
      ) : (
        <ErrorState message={batches.error?.message ?? "Something went wrong"} onRetry={() => void batches.refetch()} />
      )}
    </section>
  );
}
