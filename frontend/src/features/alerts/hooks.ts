import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "../../shared/api";
import { tankKeys } from "../tanks/api";
import { acknowledgeAlert, alertKeys, fetchAlerts } from "./api";
import type { AlertFilters } from "./api";
import { applyAlert } from "./cache";

export function useAlertsQuery(filters: AlertFilters) {
  return useQuery({
    queryKey: alertKeys.list(filters),
    queryFn: ({ signal }) => fetchAlerts(filters, signal),
  });
}

/**
 * Acknowledge sends the version the user saw. Success patches the cached lists right away and
 * refreshes the tanks; a conflict means the cache is stale, so the lists refetch.
 */
export function useAcknowledgeAlert() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: acknowledgeAlert,
    onSuccess: async (alert) => {
      applyAlert(queryClient, alert);
      await queryClient.invalidateQueries({ queryKey: tankKeys.all });
    },
    onError: async (error) => {
      if (error instanceof ApiError && error.status === 409) {
        await queryClient.invalidateQueries({ queryKey: alertKeys.lists() });
      }
    },
  });
}

export function acknowledgeErrorMessage(error: Error | null): string | null {
  if (error === null) return null;
  if (error instanceof ApiError && error.status === 409) {
    return error.detail[0]?.field === "version"
      ? "This alert changed in the meantime. It was refreshed; try again."
      : "This alert was already resolved.";
  }
  return error.message;
}
