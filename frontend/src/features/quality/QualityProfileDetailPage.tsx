import { useMemo, useState } from "react";
import { Link, useParams } from "react-router";
import { ApiError } from "../../shared/api";
import type { QualitySpec } from "../../shared/api";
import { usePermissions } from "../auth";
import { ErrorState } from "../tanks/components/ErrorState";
import { SpecForm } from "./components/SpecForm";
import { SpecsByStage } from "./components/SpecsByStage";
import { primaryButton } from "./components/buttons";
import { mapSpecErrors, toSpecBody } from "./form";
import type { SpecValues } from "./form";
import {
  useQualityParametersQuery,
  useQualityProfileQuery,
  useRemoveQualitySpec,
  useSaveQualitySpec,
} from "./hooks";

const backLink = (
  <Link to="/quality-profiles" className="text-sm font-medium text-slate-700 underline">
    Back to quality profiles
  </Link>
);

/** `null`: closed; `"add"`: a new spec; a spec: that one is being edited. */
type FormState = null | "add" | QualitySpec;

export function QualityProfileDetailPage() {
  const { profileId = "" } = useParams();
  const profile = useQualityProfileQuery(profileId);
  const parameters = useQualityParametersQuery();
  const { canWriteQualityProfiles } = usePermissions();
  const save = useSaveQualitySpec(profileId);
  const remove = useRemoveQualitySpec(profileId);
  const [form, setForm] = useState<FormState>(null);
  const [confirming, setConfirming] = useState<string | null>(null);
  const serverErrors = useMemo(() => (save.error === null ? null : mapSpecErrors(save.error)), [save.error]);

  if (profile.error instanceof ApiError && profile.error.status === 404) {
    return (
      <section className="space-y-2">
        <h2 className="text-xl font-semibold tracking-tight">Quality profile not found</h2>
        <p className="text-slate-600">There is no quality profile with id "{profileId}".</p>
        {backLink}
      </section>
    );
  }
  const failed = profile.error ?? parameters.error;
  if (profile.data === undefined || parameters.data === undefined) {
    return failed !== null ? (
      <ErrorState
        message={failed.message}
        onRetry={() => {
          void profile.refetch();
          void parameters.refetch();
        }}
      />
    ) : (
      <div role="status" aria-label="Loading profile" className="h-16 animate-pulse rounded-lg bg-slate-200" />
    );
  }

  const { data } = profile;
  const open = (next: FormState) => {
    save.reset();
    setForm(next);
  };
  const submit = (values: SpecValues) => {
    if (values.stage === "") return;
    save.mutate(
      { stage: values.stage, parameter: values.parameter, body: toSpecBody(values) },
      { onSuccess: () => setForm(null) },
    );
  };

  return (
    <section className="space-y-6">
      <header className="space-y-2">
        {backLink}
        <h2 className="text-xl font-semibold tracking-tight">{data.name}</h2>
        {data.description !== null && <p className="text-sm text-slate-600">{data.description}</p>}
        {canWriteQualityProfiles && form === null && (
          <button type="button" onClick={() => open("add")} className={primaryButton}>
            Add specification
          </button>
        )}
      </header>
      {canWriteQualityProfiles && form !== null && (
        <SpecForm
          key={form === "add" ? "add" : `${form.stage}/${form.parameter}`}
          parameters={parameters.data}
          specs={data.specs}
          editing={form === "add" ? null : form}
          submitting={save.isPending}
          serverErrors={serverErrors}
          onSubmit={submit}
          onCancel={() => open(null)}
        />
      )}
      {remove.error !== null && (
        <div role="alert" className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-900">
          {remove.error.message}
        </div>
      )}
      <SpecsByStage
        specs={data.specs}
        parameters={parameters.data}
        confirming={confirming}
        onConfirmChange={(key) => {
          remove.reset();
          setConfirming(key);
        }}
        deleting={remove.isPending}
        {...(canWriteQualityProfiles
          ? {
              onEdit: (spec: QualitySpec) => open(spec),
              onDelete: (spec: QualitySpec) =>
                remove.mutate(
                  { stage: spec.stage, parameter: spec.parameter },
                  { onSettled: () => setConfirming(null) },
                ),
            }
          : {})}
      />
    </section>
  );
}
