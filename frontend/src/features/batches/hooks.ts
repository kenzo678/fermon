import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { Batch } from "../../shared/api";
import { tankKeys } from "../tanks/api";
import {
  batchKeys,
  createBatch,
  fetchBatch,
  fetchBatchTemplates,
  fetchBatches,
  finishBatch,
  startBatch,
  updateBatch,
} from "./api";
import type { BatchFilters } from "./api";
import type { CreateBatchBody, PatchBatchBody } from "./form";

export function useBatchesQuery(filters: BatchFilters) {
  return useQuery({
    queryKey: batchKeys.list(filters),
    queryFn: ({ signal }) => fetchBatches(filters, signal),
  });
}

export function useBatchQuery(batchId: string) {
  return useQuery({
    queryKey: batchKeys.detail(batchId),
    queryFn: ({ signal }) => fetchBatch(batchId, signal),
  });
}

export function useBatchTemplatesQuery() {
  // Presets are static server-side data.
  return useQuery({
    queryKey: batchKeys.templates(),
    queryFn: ({ signal }) => fetchBatchTemplates(signal),
    staleTime: Infinity,
  });
}

/**
 * A batch change can alter a tank's active batch, so lists, details and the tank queries refresh
 * together. The returned batch seeds its own detail cache so the UI updates before the refetch;
 * `onWrite` runs synchronously right before that seeding so a caller can recognize its own write
 * in the same render, never mistaking the bumped version for an external change.
 */
function useBatchMutation<Variables>(
  mutationFn: (variables: Variables) => Promise<Batch>,
  onWrite?: (batch: Batch) => void,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: async (batch) => {
      onWrite?.(batch);
      queryClient.setQueryData(batchKeys.detail(batch.id), batch);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: batchKeys.lists() }),
        queryClient.invalidateQueries({ queryKey: tankKeys.all }),
      ]);
    },
  });
}

export const useCreateBatch = () => useBatchMutation((body: CreateBatchBody) => createBatch(body));

export const useUpdateBatch = (batchId: string, onWrite?: (batch: Batch) => void) =>
  useBatchMutation((body: PatchBatchBody) => updateBatch(batchId, body), onWrite);

export const useStartBatch = (batchId: string, onWrite?: (batch: Batch) => void) =>
  useBatchMutation(() => startBatch(batchId), onWrite);

export const useFinishBatch = (batchId: string, onWrite?: (batch: Batch) => void) =>
  useBatchMutation(() => finishBatch(batchId), onWrite);
