import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router";
import { ApiError } from "../../shared/api";
import type { Batch } from "../../shared/api";
import { formatDateTime } from "../tanks/format";
import { ErrorState } from "../tanks/components/ErrorState";
import { useTanksQuery } from "../tanks/useTanksQuery";
import { BatchForm } from "./components/BatchForm";
import { StatusBadge } from "./components/StatusBadge";
import { mapServerErrors, toPatchBody, valuesFromBatch } from "./form";
import {
  useBatchQuery,
  useBatchTemplatesQuery,
  useFinishBatch,
  useStartBatch,
  useUpdateBatch,
} from "./hooks";

const backLink = (
  <Link to="/batches" className="text-sm font-medium text-slate-700 underline">
    Back to batches
  </Link>
);

const buttonClass =
  "rounded-md px-4 py-2 text-sm font-medium focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 disabled:opacity-60";

function messagesOf(error: Error): string[] {
  const { fields, general } = mapServerErrors(error);
  return [...Object.values(fields), ...general];
}

export function BatchDetailPage() {
  const { batchId = "" } = useParams();
  const batch = useBatchQuery(batchId);
  const tanks = useTanksQuery();
  const templates = useBatchTemplatesQuery();
  // The server copy the form was last (re)started from, and whether the user has unsaved edits on it.
  const [adopted, setAdopted] = useState<Batch | null>(null);
  // This page's own successful changes: the returned copy is the new truth. It is adopted by the
  // mutation hooks synchronously, in the same render as the cache write, so the bumped version
  // is never seen as an external change while lists and tanks are still refetching.
  const adoptOwn = (saved: Batch) => setAdopted(saved);
  const update = useUpdateBatch(batchId, adoptOwn);
  const start = useStartBatch(batchId, adoptOwn);
  const finish = useFinishBatch(batchId, adoptOwn);
  const [confirmingFinish, setConfirmingFinish] = useState(false);
  const [dirty, setDirty] = useState(false);
  if (adopted === null && batch.data !== undefined) setAdopted(batch.data);
  const resetUpdate = update.reset;
  const changedElsewhere = batch.data !== undefined && adopted !== null && batch.data.version !== adopted.version;
  const initialValues = useMemo(() => (adopted === null ? null : valuesFromBatch(adopted)), [adopted]);

  // A newer server copy replaces a pristine form silently; unsaved edits are kept and flagged instead.
  if (changedElsewhere && !dirty && batch.data !== undefined) setAdopted(batch.data);
  // Errors of a failed save belong to the version they were sent against: drop them when it is replaced.
  useEffect(() => {
    resetUpdate();
  }, [adopted, resetUpdate]);

  const formErrors = useMemo(
    () => (update.error === null ? null : mapServerErrors(update.error)),
    [update.error],
  );

  if (batch.error instanceof ApiError && batch.error.status === 404) {
    return (
      <section className="space-y-2">
        <h2 className="text-xl font-semibold tracking-tight">Batch not found</h2>
        <p className="text-slate-600">There is no batch with id "{batchId}".</p>
        {backLink}
      </section>
    );
  }
  if (batch.data === undefined || adopted === null || initialValues === null) {
    return batch.isPending ? (
      <div role="status" aria-label="Loading batch" className="h-16 animate-pulse rounded-lg bg-slate-200" />
    ) : (
      <ErrorState message={batch.error?.message ?? "Something went wrong"} onRetry={() => void batch.refetch()} />
    );
  }

  const data = batch.data;
  const actionError = start.error ?? finish.error;
  const reload = () => {
    resetUpdate();
    void batch.refetch().then((result) => {
      if (result.data !== undefined) setAdopted(result.data);
    });
  };
  return (
    <section className="space-y-6">
      <header className="space-y-2">
        {backLink}
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="text-xl font-semibold tracking-tight">{data.beer_name}</h2>
          <StatusBadge status={data.status} />
        </div>
        <p className="text-sm text-slate-600">
          Tank{" "}
          <Link to={`/tanks/${encodeURIComponent(data.tank_id)}`} className="font-medium underline">
            {data.tank_id}
          </Link>
          {data.started_at !== null && <> · Started {formatDateTime(data.started_at)}</>}
          {data.finished_at !== null && <> · Finished {formatDateTime(data.finished_at)}</>}
        </p>
        {data.status === "planned" && (
          <button
            type="button"
            disabled={start.isPending}
            onClick={() => start.mutate(undefined)}
            className={`${buttonClass} bg-emerald-700 text-white hover:bg-emerald-800 focus-visible:ring-emerald-500`}
          >
            Start batch
          </button>
        )}
        {data.status === "active" &&
          (confirmingFinish ? (
            <div className="space-y-2 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
              <p>Finish this batch? It will stop being monitored and can't be undone.</p>
              <div className="flex gap-2">
                <button
                  type="button"
                  disabled={finish.isPending}
                  onClick={() => finish.mutate(undefined, { onSettled: () => setConfirmingFinish(false) })}
                  className={`${buttonClass} bg-red-700 text-white hover:bg-red-800 focus-visible:ring-red-500`}
                >
                  Yes, finish batch
                </button>
                <button
                  type="button"
                  onClick={() => setConfirmingFinish(false)}
                  className={`${buttonClass} border border-slate-300 bg-white hover:bg-slate-50 focus-visible:ring-slate-500`}
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setConfirmingFinish(true)}
              className={`${buttonClass} border border-slate-300 bg-white hover:bg-slate-50 focus-visible:ring-slate-500`}
            >
              Finish batch
            </button>
          ))}
        {actionError !== null && (
          <div role="alert" className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-900">
            {messagesOf(actionError).map((message) => (
              <p key={message}>{message}</p>
            ))}
          </div>
        )}
      </header>
      {changedElsewhere && dirty && (
        <div
          role="status"
          className="flex flex-wrap items-center gap-3 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900"
        >
          <p>This batch was changed elsewhere — reload to see the latest (your unsaved edits will be lost).</p>
          <button
            type="button"
            onClick={reload}
            className={`${buttonClass} border border-amber-400 bg-white hover:bg-amber-100 focus-visible:ring-amber-500`}
          >
            Reload
          </button>
        </div>
      )}
      {tanks.data !== undefined && templates.data !== undefined ? (
        <BatchForm
          mode="edit"
          initialValues={initialValues}
          onDirtyChange={setDirty}
          tanks={tanks.data}
          templates={templates.data}
          submitLabel="Save changes"
          submitting={update.isPending}
          serverErrors={formErrors}
          readOnly={data.status === "finished"}
          errorAction={
            update.error instanceof ApiError && update.error.status === 409 ? (
              <button
                type="button"
                onClick={reload}
                className="mt-2 rounded-md border border-red-300 bg-white px-3 py-1 text-sm font-medium hover:bg-red-100"
              >
                Reload batch
              </button>
            ) : undefined
          }
          onSubmit={(values) => update.mutate(toPatchBody(values, adopted.version))}
        />
      ) : (
        <div role="status" aria-label="Loading form" className="h-64 animate-pulse rounded-lg bg-slate-200" />
      )}
    </section>
  );
}
