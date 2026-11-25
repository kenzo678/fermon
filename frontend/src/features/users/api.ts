import { apiGet, apiSend, apiSendEmpty } from "../../shared/api";
import type { Role, User } from "../../shared/api";

export const userKeys = {
  all: ["users"] as const,
  list: () => [...userKeys.all, "list"] as const,
};

export interface CreateUserBody {
  email: string;
  display_name: string;
  role: Role;
  temporary_password: string;
}

/** Partial edit; `version` is the revision the change was made against. */
export interface UpdateUserBody {
  version: number;
  role?: Role;
  active?: boolean;
  display_name?: string;
}

const userPath = (id: string) => `/users/${encodeURIComponent(id)}`;

export const fetchUsers = (signal?: AbortSignal) => apiGet<User[]>("/users", { signal });
export const createUser = (body: CreateUserBody) => apiSend<User>("POST", "/users", body);
export const updateUser = (id: string, body: UpdateUserBody) => apiSend<User>("PATCH", userPath(id), body);
export const resetUserPassword = (id: string, temporaryPassword: string) =>
  apiSendEmpty("POST", `${userPath(id)}/reset-password`, { temporary_password: temporaryPassword });
