import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { AggregatedPoint } from "../../../shared/api";

vi.mock("./TimeSeriesChart", () => ({
  TimeSeriesChart: ({ label }: { label: string }) => <div data-testid="chart">{label}</div>,
}));

import { MeasurementChart, buildSeriesOption } from "./MeasurementChart";

const points: AggregatedPoint[] = [
  { bucket_start: "2026-03-01T10:00:00Z", avg: 18.5, min: 18.1, max: 18.9, count: 12 },
  { bucket_start: "2026-03-01T10:01:00Z", avg: 18.7, min: 18.4, max: 19.0, count: 12 },
];

describe("buildSeriesOption", () => {
  const option = buildSeriesOption(points, "°C");
  const series = option.series as Array<Record<string, unknown>>;
  const byName = (name: string) => series.find((s) => s.name === name)!;

  it("uses a time x-axis", () => {
    expect((option.xAxis as { type: string }).type).toBe("time");
  });

  it("draws the average as [time, value] pairs", () => {
    expect(byName("Average").data).toEqual([
      [Date.parse("2026-03-01T10:00:00Z"), 18.5],
      [Date.parse("2026-03-01T10:01:00Z"), 18.7],
    ]);
  });

  it("draws the min-max band as stacked min + (max - min)", () => {
    const min = byName("Min").data as [number, number][];
    const spread = byName("Max").data as [number, number][];
    expect(min.map((p) => p[1])).toEqual([18.1, 18.4]);
    expect(spread[0]?.[1]).toBeCloseTo(0.8);
    expect(byName("Min").stack).toBe(byName("Max").stack);
  });

  it("formats the tooltip with value and unit", () => {
    const formatter = (option.tooltip as { formatter: (p: unknown) => string }).formatter;
    const html = formatter([{ dataIndex: 1 }]);
    expect(html).toContain("18.7 °C");
    expect(html).toContain("18.4 °C");
    expect(html).toContain("19 °C");
  });
});

describe("MeasurementChart", () => {
  it("renders the chart for a series with data", () => {
    render(<MeasurementChart title="Temperature" unit="°C" points={points} />);
    expect(screen.getByRole("heading", { name: "Temperature (°C)" })).toBeInTheDocument();
    expect(screen.getByTestId("chart")).toBeInTheDocument();
  });

  it("shows a message instead of an empty chart", () => {
    render(<MeasurementChart title="Pressure" unit="bar" points={[]} />);
    expect(screen.getByText("No data in this range")).toBeInTheDocument();
    expect(screen.queryByTestId("chart")).not.toBeInTheDocument();
  });
});
