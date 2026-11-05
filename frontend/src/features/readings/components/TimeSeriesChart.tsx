import { LineChart } from "echarts/charts";
import { DataZoomComponent, GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import { init, use as registerModules } from "echarts/core";
import type { ECharts, EChartsCoreOption } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { useEffect, useRef } from "react";

// Register only what the charts use to keep the bundle small.
registerModules([LineChart, GridComponent, TooltipComponent, DataZoomComponent, LegendComponent, CanvasRenderer]);

interface TimeSeriesChartProps {
  option: EChartsCoreOption;
  /** Accessible name of the chart. */
  label: string;
  className?: string;
}

/** Thin ECharts wrapper: init once, update via setOption, resize with the container, dispose. */
export function TimeSeriesChart({ option, label, className }: TimeSeriesChartProps) {
  const elementRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<ECharts | null>(null);

  useEffect(() => {
    const element = elementRef.current;
    if (!element) return;
    const chart = init(element);
    chartRef.current = chart;
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(element);
    return () => {
      observer.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    // Merge so refetches (background, live updates) keep the user's zoom; replace only the series.
    chartRef.current?.setOption(option, { replaceMerge: ["series"] });
  }, [option]);

  return <div ref={elementRef} role="img" aria-label={label} className={className} />;
}
