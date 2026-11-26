import type { LabAnalysis, QualityParameterInfo } from "../../../shared/api";
import { formatDateTime } from "../../tanks/format";
import { STATUS_LABELS, STATUS_STYLES, summarize } from "../format";

interface LabAnalysisCardProps {
  analysis: LabAnalysis;
  catalog: QualityParameterInfo[];
}

export function LabAnalysisCard({ analysis, catalog }: LabAnalysisCardProps) {
  const nameOf = (code: string) => catalog.find((info) => info.code === code)?.name ?? code;
  return (
    <article className="space-y-3 rounded-lg border border-slate-200 bg-white p-4">
      <header className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h5 className="text-sm font-semibold text-slate-900">{formatDateTime(analysis.sampled_at)}</h5>
        <p className="text-sm text-slate-700">{summarize(analysis.results)}</p>
      </header>
      {analysis.analyst !== null && (
        <p className="text-sm text-slate-600">
          Analyst: <span>{analysis.analyst}</span>
        </p>
      )}
      {analysis.notes !== null && <p className="text-sm text-slate-600">{analysis.notes}</p>}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th scope="col" className="py-1 pr-4 font-medium">
                Parameter
              </th>
              <th scope="col" className="py-1 pr-4 font-medium">
                Value
              </th>
              <th scope="col" className="py-1 font-medium">
                Status
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {analysis.results.map((result) => (
              <tr key={result.parameter}>
                <th scope="row" className="py-1.5 pr-4 font-medium text-slate-900">
                  {nameOf(result.parameter)}
                </th>
                <td className="py-1.5 pr-4 tabular-nums">{`${result.value} ${result.unit}`.trimEnd()}</td>
                <td className="py-1.5">
                  <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[result.status]}`}>
                    {STATUS_LABELS[result.status]}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </article>
  );
}
