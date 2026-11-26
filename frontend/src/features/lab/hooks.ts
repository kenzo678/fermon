import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { LabAnalysis } from "../../shared/api";
import { createLabAnalysis, fetchLabAnalyses, labKeys } from "./api";
import type { CreateLabAnalysisBody } from "./api";

export const useLabAnalysesQuery = (batchId: string) =>
  useQuery({
    queryKey: labKeys.batch(batchId),
    queryFn: ({ signal }) => fetchLabAnalyses(batchId, undefined, signal),
  });

/** The new analysis joins the cached list at once (oldest first); the refetch confirms it. */
export function useRecordLabAnalysis(batchId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateLabAnalysisBody) => createLabAnalysis(batchId, body),
    onSuccess: async (analysis) => {
      queryClient.setQueryData<LabAnalysis[]>(labKeys.batch(batchId), (current) =>
        [...(current ?? []).filter((a) => a.id !== analysis.id), analysis].sort((a, b) =>
          a.sampled_at.localeCompare(b.sampled_at),
        ),
      );
      await queryClient.invalidateQueries({ queryKey: labKeys.batch(batchId) });
    },
  });
}
