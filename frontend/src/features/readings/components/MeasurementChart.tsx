import type { EChartsCoreOption } from "echarts/core";
import { useMemo } from "react";
import type { AggregatedPoint } from "../../../shared/api";
import { TimeSeriesChart } from "./TimeSeriesChart";

const number = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });

/**
 * Target range of the active batch. A missing minimum draws the band from 0 (pressure only); a
 * missing maximum draws it up to the highest observed value.
 */
export interface TargetBand {
  min: number | null;
  max: number | null;
}

/**
 * Line for the average plus a min-max band (stacked min + (max - min)); with a `target`, the
 * active batch's range is shaded behind the data.
 */
export function buildSeriesOption(
  points: AggregatedPoint[],
  unit: string,
  target?: TargetBand,
): EChartsCoreOption {
  const pairs = (value: (p: AggregatedPoint) => number) =>
    points.map((p) => [Date.parse(p.bucket_start), value(p)]);
  const format = (value: number) => `${number.format(value)} ${unit}`;
  const bandColor = "#0ea5e9";

  return {
    animation: false,
    grid: { left: 8, right: 16, top: 16, bottom: 56, containLabel: true },
    legend: { data: ["Average"], bottom: 28 },
    tooltip: {
      trigger: "axis",
      formatter: (params: Array<{ dataIndex: number }>) => {
        const point = points[params[0]?.dataIndex ?? -1];
        if (!point) return "";
        return [
          new Date(point.bucket_start).toLocaleString("en-GB"),
          `Average: ${format(point.avg)}`,
          `Min: ${format(point.min)}`,
          `Max: ${format(point.max)}`,
        ].join("<br/>");
      },
    },
    xAxis: { type: "time" },
    yAxis: { type: "value", scale: true, axisLabel: { formatter: (v: number) => number.format(v) } },
    dataZoom: [{ type: "inside" }, { type: "slider", height: 18, bottom: 4 }],
    series: [
      {
        name: "Min",
        type: "line",
        stack: "band",
        // Stack across signs: a cold crash can push the min below 0 °C.
        stackStrategy: "all",
        data: pairs((p) => p.min),
        symbol: "none",
        lineStyle: { opacity: 0 },
        tooltip: { show: false },
      },
      {
        name: "Max",
        type: "line",
        stack: "band",
        // Stack across signs: a cold crash can push the min below 0 °C.
        stackStrategy: "all",
        data: pairs((p) => p.max - p.min),
        symbol: "none",
        lineStyle: { opacity: 0 },
        areaStyle: { color: bandColor, opacity: 0.18 },
        tooltip: { show: false },
      },
      {
        name: "Average",
        type: "line",
        data: pairs((p) => p.avg),
        symbol: "none",
        lineStyle: { width: 2, color: bandColor },
        itemStyle: { color: bandColor },
        ...(target && {
          markArea: {
            silent: true,
            itemStyle: { color: "#22c55e", opacity: 0.12 },
            data: [[{ yAxis: target.min ?? 0 }, { yAxis: target.max ?? Math.max(...points.map((p) => p.max)) }]],
          },
        }),
      },
    ],
  };
}

interface MeasurementChartProps {
  title: string;
  unit: string;
  points: AggregatedPoint[];
  target?: TargetBand;
}

export function MeasurementChart({ title, unit, points, target }: MeasurementChartProps) {
  // Depend on the primitives: callers build `target` inline on every render.
  const min = target?.min ?? null;
  const max = target?.max ?? null;
  const hasTarget = target !== undefined;
  const option = useMemo(
    () => buildSeriesOption(points, unit, hasTarget ? { min, max } : undefined),
    [points, unit, hasTarget, min, max],
  );
  const heading = `${title} (${unit})`;
  return (
    <section
      className="rounded-lg border border-slate-200 bg-white p-4"
      // The band is drawn on a canvas; this makes the configured range observable (e2e, tooling).
      data-target-band={min === null && max === null ? undefined : `${min ?? ""}..${max ?? ""}`}
    >
      <h3 className="text-base font-semibold">{heading}</h3>
      {points.length === 0 ? (
        <p className="mt-4 text-sm text-slate-600">No data in this range</p>
      ) : (
        <TimeSeriesChart option={option} label={`${heading} over time`} className="mt-2 h-64 w-full" />
      )}
    </section>
  );
}
