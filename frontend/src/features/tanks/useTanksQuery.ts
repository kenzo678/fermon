import { useQuery } from "@tanstack/react-query";
import { fetchTanks, tankKeys } from "./api";

export function useTanksQuery() {
  return useQuery({
    queryKey: tankKeys.list(),
    queryFn: ({ signal }) => fetchTanks(signal),
  });
}
