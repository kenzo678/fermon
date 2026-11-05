import type { Measurement, Reading, Tank } from "../shared/api";

const UNITS: Record<Measurement, string> = {
  temperature: "celsius",
  pressure: "bar",
  alcohol: "percent_abv",
};

export function makeReading(
  tankId: string,
  measurement: Measurement,
  value: number,
  recordedAt = "2026-03-01T10:00:00Z",
): Reading {
  return {
    tank_id: tankId,
    sensor_id: `${tankId}-${measurement}`,
    measurement,
    value,
    unit: UNITS[measurement],
    recorded_at: recordedAt,
  };
}

export function makeTank(id: string, overrides: Partial<Tank> = {}): Tank {
  return {
    id,
    display_name: null,
    first_seen_at: "2026-02-01T08:00:00Z",
    latest: {
      temperature: makeReading(id, "temperature", 18.46),
      pressure: makeReading(id, "pressure", 1.234),
      alcohol: makeReading(id, "alcohol", 4.25),
    },
    ...overrides,
  };
}
