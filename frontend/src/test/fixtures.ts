import type {
  Alert,
  Batch,
  Measurement,
  QualityParameterInfo,
  QualityProfile,
  QualitySpec,
  Reading,
  Role,
  Tank,
  User,
} from "../shared/api";

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
    active_batch: null,
    open_alerts: 0,
    latest: {
      temperature: makeReading(id, "temperature", 18.46),
      pressure: makeReading(id, "pressure", 1.234),
      alcohol: makeReading(id, "alcohol", 4.25),
    },
    ...overrides,
  };
}

export function makeBatch(overrides: Partial<Batch> = {}): Batch {
  return {
    id: "b1",
    tank_id: "tank-1",
    beer_name: "Pale Ale",
    style: "American Pale Ale",
    template: "ale",
    targets: {
      temperature_min: 18,
      temperature_max: 21,
      pressure_max: 1,
      pressure_min: null,
      expected_final_abv: 5,
    },
    status: "planned",
    planned_start: "2026-03-01T10:00:00Z",
    expected_end: null,
    started_at: null,
    finished_at: null,
    notes: null,
    created_at: "2026-02-28T10:00:00Z",
    version: 1,
    ...overrides,
  };
}

export function makeAlert(overrides: Partial<Alert> = {}): Alert {
  return {
    id: "a1",
    tank_id: "tank-1",
    batch_id: "b1",
    kind: "out_of_range",
    measurement: "temperature",
    status: "open",
    opened_at: "2026-03-01T12:00:00Z",
    acknowledged_at: null,
    resolved_at: null,
    details: { bound: "below", observed: 19.1, target_min: 30, target_max: 35 },
    version: 1,
    ...overrides,
  };
}

export function makeUser(overrides: Partial<User> = {}): User {
  return {
    id: "user-1",
    email: "admin@example.com",
    display_name: "Ada Admin",
    role: "admin" as Role,
    must_change_password: false,
    active: true,
    version: 1,
    ...overrides,
  };
}

export const QUALITY_CATALOG: QualityParameterInfo[] = [
  { code: "original_extract", name: "Original extract", unit: "°P", minimum: 0, maximum: 30 },
  { code: "ph", name: "pH", unit: "pH", minimum: 0, maximum: 14 },
  { code: "color", name: "Color", unit: "EBC", minimum: 0, maximum: 300 },
  { code: "wort_oxygen", name: "Wort oxygen", unit: "ppm", minimum: 0, maximum: 50 },
];

export function makeQualitySpec(overrides: Partial<QualitySpec> = {}): QualitySpec {
  return {
    stage: "brewhouse",
    parameter: "ph",
    unit: "pH",
    acceptance: { min: 5, max: 5.6 },
    internal: { min: 5.1, max: 5.5 },
    target: 5.3,
    ...overrides,
  };
}

export function makeQualityProfile(overrides: Partial<QualityProfile> = {}): QualityProfile {
  return {
    id: "p1",
    name: "House lager",
    description: null,
    created_at: "2026-03-01T10:00:00Z",
    specs: [],
    ...overrides,
  };
}
