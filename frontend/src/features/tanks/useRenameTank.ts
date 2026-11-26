import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { Tank } from "../../shared/api";
import { renameTank, tankKeys } from "./api";

/**
 * The answer is the whole tank overview, so it replaces the cached detail and its entry in the list
 * at once (every `display_name ?? id` reads from those); the invalidation then confirms them.
 */
export function useRenameTank(tankId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (displayName: string | null) => renameTank(tankId, displayName),
    onSuccess: async (tank) => {
      queryClient.setQueryData(tankKeys.detail(tankId), tank);
      queryClient.setQueryData<Tank[]>(tankKeys.list(), (current) =>
        current?.map((item) => (item.id === tank.id ? tank : item)),
      );
      await queryClient.invalidateQueries({ queryKey: tankKeys.all });
    },
  });
}
