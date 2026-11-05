import { useQuery } from "@tanstack/react-query";
import { fetchAggregatedReadings, readingKeys } from "./api";
import type { RangeValue } from "./range";

export function useAggregatedReadingsQuery(tankId: string, range: RangeValue) {
  return useQuery({
    queryKey: readingKeys.aggregated(tankId, range),
    queryFn: ({ signal }) => fetchAggregatedReadings(tankId, range, signal),
  });
}
