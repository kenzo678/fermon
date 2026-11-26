import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router";
import { fieldMessages } from "../../shared/api";
import type { QualityProfile } from "../../shared/api";
import { usePermissions } from "../auth";
import { ErrorState } from "../tanks/components/ErrorState";
import { formatDateTime } from "../tanks/format";
import { NewProfileForm } from "./components/NewProfileForm";
import { primaryButton } from "./components/buttons";
import { useCreateQualityProfile, useQualityProfilesQuery, useQualityTemplatesQuery } from "./hooks";

const linkClass = "font-medium underline";
const specCount = (profile: QualityProfile) =>
  `${profile.specs.length} ${profile.specs.length === 1 ? "spec" : "specs"}`;

function ProfileTable({ profiles }: { profiles: QualityProfile[] }) {
  return (
    <table className="hidden w-full text-left text-sm md:table">
      <caption className="sr-only">Quality profiles</caption>
      <thead className="border-b border-slate-200 text-xs uppercase text-slate-500">
        <tr>
          {["Profile", "Specifications", "Created"].map((heading) => (
            <th key={heading} scope="col" className="px-3 py-2 font-medium">
              {heading}
            </th>
          ))}
        </tr>
      </thead>
      <tbody className="divide-y divide-slate-100 bg-white">
        {profiles.map((profile) => (
          <tr key={profile.id}>
            <th scope="row" className="px-3 py-2 font-medium">
              <Link to={`/quality-profiles/${encodeURIComponent(profile.id)}`} className={linkClass}>
                {profile.name}
              </Link>
            </th>
            <td className="px-3 py-2 tabular-nums">{specCount(profile)}</td>
            <td className="px-3 py-2">{formatDateTime(profile.created_at)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ProfileCards({ profiles }: { profiles: QualityProfile[] }) {
  return (
    <ul className="space-y-3 md:hidden">
      {profiles.map((profile) => (
        <li key={profile.id} className="space-y-1 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <Link to={`/quality-profiles/${encodeURIComponent(profile.id)}`} className={linkClass}>
            {profile.name}
          </Link>
          <p className="text-sm text-slate-600">{specCount(profile)}</p>
        </li>
      ))}
    </ul>
  );
}

export function QualityProfilesPage() {
  const navigate = useNavigate();
  const profiles = useQualityProfilesQuery();
  const templates = useQualityTemplatesQuery();
  const create = useCreateQualityProfile();
  const { canWriteQualityProfiles } = usePermissions();
  const [creating, setCreating] = useState(false);
  const serverErrors = useMemo(() => (create.error === null ? null : fieldMessages(create.error)), [create.error]);

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-xl font-semibold tracking-tight">Quality profiles</h2>
        {canWriteQualityProfiles && !creating && (
          <button type="button" onClick={() => setCreating(true)} className={primaryButton}>
            New profile
          </button>
        )}
      </div>
      {canWriteQualityProfiles && creating && (
        <NewProfileForm
          templates={templates.data ?? []}
          submitting={create.isPending}
          serverErrors={serverErrors}
          onCancel={() => {
            create.reset();
            setCreating(false);
          }}
          onSubmit={(body) =>
            create.mutate(body, {
              onSuccess: (profile) => void navigate(`/quality-profiles/${encodeURIComponent(profile.id)}`),
            })
          }
        />
      )}
      {profiles.data !== undefined ? (
        profiles.data.length === 0 ? (
          <p className="rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-600">
            No quality profiles yet
          </p>
        ) : (
          <>
            <ProfileTable profiles={profiles.data} />
            <ProfileCards profiles={profiles.data} />
          </>
        )
      ) : profiles.isPending ? (
        <div role="status" aria-label="Loading profiles" className="h-32 animate-pulse rounded-lg bg-slate-200" />
      ) : (
        <ErrorState message={profiles.error?.message ?? "Something went wrong"} onRetry={() => void profiles.refetch()} />
      )}
    </section>
  );
}
