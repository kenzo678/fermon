import { apiGet } from "../../shared/api";
import type { AggregatedReadings } from "../../shared/api";
import { rangeToQuery } from "./range";
import type { RangeValue } from "./range";

export const readingKeys = {
  all: ["readings"] as const,
  aggregated: (tankId: string, range: RangeValue) =>
    [...readingKeys.all, "aggregated", tankId, range] as const,
};

/** All three measurements in one call; the window is anchored at "now" per request. */
export function fetchAggregatedReadings(
  tankId: string,
  range: RangeValue,
  signal?: AbortSignal,
  now: number = Date.now(),
): Promise<AggregatedReadings> {
  return apiGet<AggregatedReadings>(
    `/tanks/${encodeURIComponent(tankId)}/readings/aggregated`,
    { params: rangeToQuery(range, now), signal },
  );
}
