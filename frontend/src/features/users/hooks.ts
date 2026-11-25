import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "../../shared/api";
import { sessionKeys } from "../auth/api";
import { createUser, fetchUsers, resetUserPassword, updateUser, userKeys } from "./api";
import type { CreateUserBody, UpdateUserBody } from "./api";

export const useUsersQuery = () =>
  useQuery({ queryKey: userKeys.list(), queryFn: ({ signal }) => fetchUsers(signal) });

export function useCreateUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateUserBody) => createUser(body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: userKeys.all }),
  });
}

/** One row's edits; the session is refreshed too because an admin may have edited themselves. */
export function useUpdateUser(userId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: UpdateUserBody) => updateUser(userId, body),
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: userKeys.all }),
        queryClient.invalidateQueries({ queryKey: sessionKeys.all }),
      ]),
  });
}

export const useResetPassword = (userId: string) =>
  useMutation({ mutationFn: (temporaryPassword: string) => resetUserPassword(userId, temporaryPassword) });

/** A stale `version` is the one conflict worth its own explanation and a reload action. */
export const isVersionConflict = (error: Error | null): boolean =>
  error instanceof ApiError &&
  error.status === 409 &&
  error.detail.some((item) => item.field === "version");
