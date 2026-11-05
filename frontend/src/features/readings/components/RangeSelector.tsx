import { RANGES } from "../range";
import type { RangeValue } from "../range";

interface RangeSelectorProps {
  value: RangeValue;
  onChange: (range: RangeValue) => void;
}

export function RangeSelector({ value, onChange }: RangeSelectorProps) {
  return (
    <div role="radiogroup" aria-label="Time range" className="inline-flex flex-wrap gap-1">
      {RANGES.map((range) => (
        <label
          key={range.value}
          className="cursor-pointer rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 has-[:checked]:border-slate-900 has-[:checked]:bg-slate-900 has-[:checked]:text-white has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-sky-500"
        >
          <input
            type="radio"
            name="range"
            value={range.value}
            checked={value === range.value}
            onChange={() => onChange(range.value)}
            className="sr-only"
          />
          {range.label}
        </label>
      ))}
    </div>
  );
}
