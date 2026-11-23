import { useMemo } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { ErrorState } from "../tanks/components/ErrorState";
import { useTanksQuery } from "../tanks/useTanksQuery";
import { BatchForm } from "./components/BatchForm";
import { emptyValues, mapServerErrors, toCreateBody, toLocalInput } from "./form";
import { useBatchTemplatesQuery, useCreateBatch } from "./hooks";

export function NewBatchPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const tanks = useTanksQuery();
  const templates = useBatchTemplatesQuery();
  const create = useCreateBatch();
  const serverErrors = useMemo(
    () => (create.error === null ? null : mapServerErrors(create.error)),
    [create.error],
  );
  // The default start is "now"; computed once so the form's initial state is stable.
  const initialValues = useMemo(
    () => ({
      ...emptyValues(toLocalInput(new Date().toISOString())),
      tank_id: searchParams.get("tank") ?? "",
    }),
    [searchParams],
  );

  const failed = tanks.error ?? templates.error;
  return (
    <section className="space-y-4">
      <header className="space-y-1">
        <Link to="/batches" className="text-sm font-medium text-slate-700 underline">
          Back to batches
        </Link>
        <h2 className="text-xl font-semibold tracking-tight">New batch</h2>
      </header>
      {tanks.data !== undefined && templates.data !== undefined ? (
        <BatchForm
          mode="create"
          initialValues={initialValues}
          tanks={tanks.data}
          templates={templates.data}
          submitLabel="Create batch"
          submitting={create.isPending}
          serverErrors={serverErrors}
          onSubmit={(values) =>
            create.mutate(toCreateBody(values), {
              onSuccess: (batch) => void navigate(`/batches/${encodeURIComponent(batch.id)}`),
            })
          }
        />
      ) : failed !== null ? (
        <ErrorState
          message={failed.message}
          onRetry={() => {
            void tanks.refetch();
            void templates.refetch();
          }}
        />
      ) : (
        <div role="status" aria-label="Loading form" className="h-64 animate-pulse rounded-lg bg-slate-200" />
      )}
    </section>
  );
}
