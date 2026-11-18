import type { AlertKind, AlertStatus, Tank } from "../../../shared/api";
import { controlClass } from "../../batches/components/Field";
import { KIND_LABELS, KIND_ORDER, STATUS_LABELS, STATUS_ORDER } from "../format";

interface AlertFiltersBarProps {
  statuses: AlertStatus[];
  tankId: string;
  kind: AlertKind | "";
  tanks: Tank[];
  onToggleStatus: (status: AlertStatus) => void;
  onTankChange: (tankId: string) => void;
  onKindChange: (kind: AlertKind | "") => void;
}

export function AlertFiltersBar({
  statuses,
  tankId,
  kind,
  tanks,
  onToggleStatus,
  onTankChange,
  onKindChange,
}: AlertFiltersBarProps) {
  return (
    <div className="flex flex-wrap items-end gap-4">
      <fieldset>
        <legend className="mb-1 text-sm font-medium">Status</legend>
        <div className="flex gap-3">
          {STATUS_ORDER.map((status) => (
            <label key={status} className="flex items-center gap-1.5 text-sm">
              <input type="checkbox" checked={statuses.includes(status)} onChange={() => onToggleStatus(status)} />
              {STATUS_LABELS[status]}
            </label>
          ))}
        </div>
      </fieldset>
      <div>
        <label htmlFor="alerts-filter-tank" className="mb-1 block text-sm font-medium">
          Tank
        </label>
        <select id="alerts-filter-tank" value={tankId} onChange={(e) => onTankChange(e.target.value)} className={controlClass}>
          <option value="">All tanks</option>
          {tanks.map((tank) => (
            <option key={tank.id} value={tank.id}>
              {tank.display_name ?? tank.id}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label htmlFor="alerts-filter-kind" className="mb-1 block text-sm font-medium">
          Kind
        </label>
        <select
          id="alerts-filter-kind"
          value={kind}
          onChange={(e) => onKindChange(e.target.value as AlertKind | "")}
          className={controlClass}
        >
          <option value="">All kinds</option>
          {KIND_ORDER.map((value) => (
            <option key={value} value={value}>
              {KIND_LABELS[value]}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}
