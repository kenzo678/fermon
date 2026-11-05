import { render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const chart = { setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn() };
vi.mock("echarts/core", () => ({ init: vi.fn(() => chart), use: vi.fn() }));

import { init } from "echarts/core";
import { TimeSeriesChart } from "./TimeSeriesChart";

let resizeCallback: (() => void) | undefined;
const observe = vi.fn();
const disconnect = vi.fn();

beforeEach(() => {
  vi.stubGlobal(
    "ResizeObserver",
    class {
      constructor(callback: () => void) {
        resizeCallback = callback;
      }
      observe = observe;
      disconnect = disconnect;
    },
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("TimeSeriesChart", () => {
  it("inits ECharts on its element and applies the option", () => {
    const option = { series: [] };
    const { getByRole } = render(<TimeSeriesChart option={option} label="Temperature chart" />);
    const element = getByRole("img", { name: "Temperature chart" });
    expect(init).toHaveBeenCalledWith(element);
    // Merge (not replace) so a refetch keeps the user's zoom; only the series are swapped.
    expect(chart.setOption).toHaveBeenCalledWith(option, { replaceMerge: ["series"] });
  });

  it("re-applies the option on update without re-initializing", () => {
    const { rerender } = render(<TimeSeriesChart option={{ a: 1 }} label="c" />);
    rerender(<TimeSeriesChart option={{ a: 2 }} label="c" />);
    expect(init).toHaveBeenCalledTimes(1);
    expect(chart.setOption).toHaveBeenLastCalledWith({ a: 2 }, { replaceMerge: ["series"] });
  });

  it("resizes the chart when its container resizes", () => {
    render(<TimeSeriesChart option={{}} label="c" />);
    expect(observe).toHaveBeenCalled();
    resizeCallback?.();
    expect(chart.resize).toHaveBeenCalledTimes(1);
  });

  it("disposes the chart and stops observing on unmount", () => {
    const { unmount } = render(<TimeSeriesChart option={{}} label="c" />);
    unmount();
    expect(disconnect).toHaveBeenCalled();
    expect(chart.dispose).toHaveBeenCalledTimes(1);
  });
});
