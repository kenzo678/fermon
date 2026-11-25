import type { Role } from "../../shared/api";

export const ROLES: Array<{ value: Role; label: string }> = [
  { value: "admin", label: "Admin" },
  { value: "brewer", label: "Brewer" },
  { value: "viewer", label: "Viewer" },
];
