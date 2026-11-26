import type { QualityParameterInfo, QualitySpec, QualityStage } from "../../../shared/api";
import { STAGE_LABELS, STAGE_ORDER, formatRange, formatTarget } from "../format";
import { dangerButton, secondaryButton } from "./buttons";

interface SpecsByStageProps {
  specs: QualitySpec[];
  parameters: QualityParameterInfo[];
  /** Write controls (edit, delete) appear only when handlers are given. */
  onEdit?: (spec: QualitySpec) => void;
  onDelete?: (spec: QualitySpec) => void;
  /** `stage/parameter` of the spec awaiting a delete confirmation. */
  confirming: string | null;
  onConfirmChange: (key: string | null) => void;
  deleting: boolean;
}

const keyOf = (spec: QualitySpec) => `${spec.stage}/${spec.parameter}`;
const smallButton = "px-2 py-1 text-xs";

interface RowProps extends Omit<SpecsByStageProps, "specs" | "parameters"> {
  spec: QualitySpec;
  name: string;
}

function Actions({ spec, name, onEdit, onDelete, confirming, onConfirmChange, deleting }: RowProps) {
  if (onEdit === undefined || onDelete === undefined) return null;
  if (confirming === keyOf(spec)) {
    return (
      <span className="flex flex-wrap items-center gap-2">
        <span className="text-sm">Delete {name}?</span>
        <button
          type="button"
          disabled={deleting}
          onClick={() => onDelete(spec)}
          className={`${dangerButton} ${smallButton}`}
        >
          Yes, delete {name}
        </button>
        <button type="button" onClick={() => onConfirmChange(null)} className={`${secondaryButton} ${smallButton}`}>
          Cancel
        </button>
      </span>
    );
  }
  return (
    <span className="flex gap-2">
      <button type="button" aria-label={`Edit ${name}`} onClick={() => onEdit(spec)} className={`${secondaryButton} ${smallButton}`}>
        Edit
      </button>
      <button
        type="button"
        aria-label={`Delete ${name}`}
        onClick={() => onConfirmChange(keyOf(spec))}
        className={`${secondaryButton} ${smallButton}`}
      >
        Delete
      </button>
    </span>
  );
}

function StageTable({ label, specs, nameOf, ...actions }: { label: string; specs: QualitySpec[]; nameOf: (spec: QualitySpec) => string } & Omit<SpecsByStageProps, "specs" | "parameters">) {
  const writable = actions.onEdit !== undefined;
  const headings = ["Parameter", "Acceptance", "Internal", "Target", ...(writable ? ["Actions"] : [])];
  return (
    <table className="hidden w-full text-left text-sm md:table">
      <caption className="sr-only">{label}</caption>
      <thead className="border-b border-slate-200 text-xs uppercase text-slate-500">
        <tr>
          {headings.map((heading) => (
            <th key={heading} scope="col" className="px-3 py-2 font-medium">
              {heading}
            </th>
          ))}
        </tr>
      </thead>
      <tbody className="divide-y divide-slate-100 bg-white">
        {specs.map((spec) => (
          <tr key={keyOf(spec)}>
            <th scope="row" className="px-3 py-2 font-medium">
              {nameOf(spec)}
            </th>
            <td className="px-3 py-2 tabular-nums">{formatRange(spec.acceptance, spec.unit)}</td>
            <td className="px-3 py-2 tabular-nums">{formatRange(spec.internal, spec.unit)}</td>
            <td className="px-3 py-2 tabular-nums">{formatTarget(spec.target, spec.unit)}</td>
            {writable && (
              <td className="px-3 py-2">
                <Actions spec={spec} name={nameOf(spec)} {...actions} />
              </td>
            )}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function StageCards({ specs, nameOf, ...actions }: { specs: QualitySpec[]; nameOf: (spec: QualitySpec) => string } & Omit<SpecsByStageProps, "specs" | "parameters">) {
  return (
    <ul className="space-y-3 md:hidden">
      {specs.map((spec) => (
        <li key={keyOf(spec)} className="space-y-1 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <p className="font-medium">{nameOf(spec)}</p>
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 text-sm tabular-nums text-slate-600">
            <dt>Acceptance</dt>
            <dd>{formatRange(spec.acceptance, spec.unit)}</dd>
            <dt>Internal</dt>
            <dd>{formatRange(spec.internal, spec.unit)}</dd>
            <dt>Target</dt>
            <dd>{formatTarget(spec.target, spec.unit)}</dd>
          </dl>
          <Actions spec={spec} name={nameOf(spec)} {...actions} />
        </li>
      ))}
    </ul>
  );
}

/** Specs grouped by stage in process order: a table on wide screens, cards on small ones. */
export function SpecsByStage({ specs, parameters, ...actions }: SpecsByStageProps) {
  const nameOf = (spec: QualitySpec) => parameters.find((item) => item.code === spec.parameter)?.name ?? spec.parameter;
  return (
    <div className="space-y-6">
      {STAGE_ORDER.map((stage: QualityStage) => {
        const inStage = specs.filter((spec) => spec.stage === stage);
        return (
          <section key={stage} aria-labelledby={`stage-${stage}`} className="space-y-2">
            <h3 id={`stage-${stage}`} className="text-base font-semibold">
              {STAGE_LABELS[stage]}
            </h3>
            {inStage.length === 0 ? (
              <p className="rounded-lg border border-dashed border-slate-300 bg-white p-4 text-sm text-slate-600">
                No specs at this stage
              </p>
            ) : (
              <>
                <StageTable label={STAGE_LABELS[stage]} specs={inStage} nameOf={nameOf} {...actions} />
                <StageCards specs={inStage} nameOf={nameOf} {...actions} />
              </>
            )}
          </section>
        );
      })}
    </div>
  );
}
