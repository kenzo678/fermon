import { describe, expect, it } from "vitest";
import { formatDateTime } from "../tanks/format";
import { makeAlert } from "../../test/fixtures";
import { alertMessage, resolutionNote } from "./format";

describe("alertMessage", () => {
  it("describes a temperature below the target", () => {
    expect(alertMessage(makeAlert())).toBe("Temperature below target (observed 19.1 °C, target 30–35 °C)");
  });

  it("describes a temperature above the target", () => {
    const alert = makeAlert({ details: { bound: "above", observed: 36.24, target_min: 30, target_max: 35 } });
    expect(alertMessage(alert)).toBe("Temperature above target (observed 36.2 °C, target 30–35 °C)");
  });

  it("describes pressure with an open lower bound", () => {
    const alert = makeAlert({
      measurement: "pressure",
      details: { bound: "above", observed: 1.351, target_min: null, target_max: 1 },
    });
    expect(alertMessage(alert)).toBe("Pressure above target (observed 1.35 bar, target up to 1 bar)");
  });

  it("describes a pressure below a minimum without a maximum", () => {
    const alert = makeAlert({
      measurement: "pressure",
      details: { bound: "below", observed: 0.2, target_min: 0.5, target_max: null },
    });
    expect(alertMessage(alert)).toBe("Pressure below target (observed 0.20 bar, target at least 0.5 bar)");
  });

  it("degrades gracefully when the details are incomplete", () => {
    const alert = makeAlert({ details: {} });
    expect(alertMessage(alert)).toBe("Temperature out of range");
  });

  it("describes a silent sensor from its last reading", () => {
    const alert = makeAlert({
      kind: "silent_sensor",
      measurement: null,
      details: { last_reading_at: "2026-03-01T12:00:00Z" },
    });
    expect(alertMessage(alert)).toBe(`No readings since ${formatDateTime("2026-03-01T12:00:00Z")}`);
  });

  it("describes a silent sensor that never reported", () => {
    const alert = makeAlert({ kind: "silent_sensor", measurement: null, details: { last_reading_at: null } });
    expect(alertMessage(alert)).toBe("No readings since the batch started");
  });
});

describe("resolutionNote", () => {
  it("is null for recovered and unresolved alerts", () => {
    expect(resolutionNote(makeAlert())).toBeNull();
    expect(resolutionNote(makeAlert({ status: "resolved", resolved_at: "2026-03-01T12:30:00Z" }))).toBeNull();
  });

  it("explains the special resolutions", () => {
    const resolved = { status: "resolved", resolved_at: "2026-03-01T12:30:00Z" } as const;
    expect(resolutionNote(makeAlert({ ...resolved, details: { resolution: "batch_finished" } }))).toBe(
      "Resolved because the batch was finished",
    );
    expect(resolutionNote(makeAlert({ ...resolved, details: { resolution: "late_data" } }))).toBe(
      "Resolved by late-arriving data",
    );
  });
});
