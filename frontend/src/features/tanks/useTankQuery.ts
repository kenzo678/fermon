import { useQuery } from "@tanstack/react-query";
import { fetchTank, tankKeys } from "./api";

export function useTankQuery(tankId: string) {
  return useQuery({
    queryKey: tankKeys.detail(tankId),
    queryFn: ({ signal }) => fetchTank(tankId, signal),
  });
}
