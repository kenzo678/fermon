import { useState } from "react";
import type { Batch, QualityProfile } from "../../shared/api";
import { usePermissions } from "../auth";
import { primaryButton } from "../quality/components/buttons";
import { STAGE_LABELS, STAGE_ORDER } from "../quality/format";
import { useQualityParametersQuery } from "../quality/hooks";
import { ErrorState } from "../tanks/components/ErrorState";
import { LabAnalysisCard } from "./components/LabAnalysisCard";
import { RecordAnalysisForm } from "./components/RecordAnalysisForm";
import { useLabAnalysesQuery } from "./hooks";

interface LabAnalysesSectionProps {
  batch: Batch;
  /** The batch's profile with its specs, to suggest the parameters worth measuring. */
  profile: QualityProfile | undefined;
}

export function LabAnalysesSection({ batch, profile }: LabAnalysesSectionProps) {
  return (
    <section aria-labelledby="lab-analyses-heading" className="space-y-4">
      <h3 id="lab-analyses-heading" className="text-lg font-semibold tracking-tight">
        Lab analyses
      </h3>
      {batch.status === "planned" ? (
        <p className="text-sm text-slate-600">Lab analyses can be recorded once the batch is active.</p>
      ) : (
        <LabAnalysesPanel batchId={batch.id} profile={profile} />
      )}
    </section>
  );
}

function LabAnalysesPanel({ batchId, profile }: { batchId: string; profile: QualityProfile | undefined }) {
  const { canRecordLabAnalyses } = usePermissions();
  const analyses = useLabAnalysesQuery(batchId);
  const catalog = useQualityParametersQuery();
  const [recording, setRecording] = useState(false);
  const [recorded, setRecorded] = useState(false);

  const failed = analyses.error ?? catalog.error;
  if (analyses.data === undefined || catalog.data === undefined) {
    return failed !== null ? (
      <ErrorState
        message={failed.message}
        onRetry={() => {
          void analyses.refetch();
          void catalog.refetch();
        }}
      />
    ) : (
      <div role="status" aria-label="Loading analyses" className="h-24 animate-pulse rounded-lg bg-slate-200" />
    );
  }

  return (
    <div className="space-y-4">
      {canRecordLabAnalyses &&
        (recording ? (
          <RecordAnalysisForm
            batchId={batchId}
            profile={profile}
            catalog={catalog.data}
            onRecorded={() => {
              setRecording(false);
              setRecorded(true);
            }}
            onCancel={() => setRecording(false)}
          />
        ) : (
          <button
            type="button"
            onClick={() => {
              setRecorded(false);
              setRecording(true);
            }}
            className={primaryButton}
          >
            Record analysis
          </button>
        ))}
      {recorded && (
        <p role="status" className="rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900">
          Analysis recorded.
        </p>
      )}
      {analyses.data.length === 0 ? (
        <p className="rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-600">
          No analyses recorded yet
        </p>
      ) : (
        STAGE_ORDER.map((stage) => {
          const ofStage = analyses.data.filter((analysis) => analysis.stage === stage);
          if (ofStage.length === 0) return null;
          return (
            <section key={stage} aria-labelledby={`lab-stage-${stage}`} className="space-y-2">
              <h4 id={`lab-stage-${stage}`} className="text-sm font-semibold text-slate-900">
                {STAGE_LABELS[stage]}
              </h4>
              {ofStage.map((analysis) => (
                <LabAnalysisCard key={analysis.id} analysis={analysis} catalog={catalog.data} />
              ))}
            </section>
          );
        })
      )}
    </div>
  );
}
