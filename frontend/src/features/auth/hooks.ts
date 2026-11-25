import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo } from "react";
import type { Role } from "../../shared/api";
import { changePassword, dropPrivateData, fetchSession, login, logout, sessionKeys } from "./api";
import * as permissions from "./permissions";

/** How long a known session is trusted before a focus or mount refetch re-checks it. */
const SESSION_STALE_MS = 60_000;

/** `data` is the user, `null` when signed out, `undefined` while the first answer is pending. */
export function useSession() {
  return useQuery({
    queryKey: sessionKeys.current(),
    queryFn: ({ signal }) => fetchSession(signal),
    staleTime: SESSION_STALE_MS,
  });
}

export interface Permissions {
  role: Role | null;
  canManageUsers: boolean;
  canWriteBatches: boolean;
  canAcknowledgeAlerts: boolean;
  canWriteQualityProfiles: boolean;
  canRecordLabAnalyses: boolean;
  canDownloadReports: boolean;
}

/** What the current user may do; everything is denied without a session. */
export function usePermissions(): Permissions {
  const role = useSession().data?.role ?? null;
  return useMemo(
    () => ({
      role,
      canManageUsers: role !== null && permissions.canManageUsers(role),
      canWriteBatches: role !== null && permissions.canWriteBatches(role),
      canAcknowledgeAlerts: role !== null && permissions.canAcknowledgeAlerts(role),
      canWriteQualityProfiles: role !== null && permissions.canWriteQualityProfiles(role),
      canRecordLabAnalyses: role !== null && permissions.canRecordLabAnalyses(role),
      canDownloadReports: role !== null && permissions.canDownloadReports(role),
    }),
    [role],
  );
}

export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: login,
    onSuccess: (user) => {
      dropPrivateData(queryClient);
      queryClient.setQueryData(sessionKeys.current(), user);
    },
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: logout,
    // Even when the request fails the client must stop showing the private data.
    onSettled: () => {
      dropPrivateData(queryClient);
      queryClient.setQueryData(sessionKeys.current(), null);
    },
  });
}

export function useChangePassword() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: changePassword,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: sessionKeys.all }),
  });
}
