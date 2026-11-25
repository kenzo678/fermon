import type { Role } from "../../shared/api";

// Mirrors backend/src/fermon/identity/domain/role.py. The server enforces every rule; these
// predicates only decide what the UI offers, so keep the two tables in step.
const BREWING: readonly Role[] = ["admin", "brewer"];

export const canManageUsers = (role: Role): boolean => role === "admin";
export const canWriteBatches = (role: Role): boolean => BREWING.includes(role);
export const canAcknowledgeAlerts = (role: Role): boolean => BREWING.includes(role);
export const canWriteQualityProfiles = (role: Role): boolean => BREWING.includes(role);
export const canRecordLabAnalyses = (role: Role): boolean => BREWING.includes(role);
// Every role, viewers included, may download reports.
const REPORT_READERS: readonly Role[] = ["admin", "brewer", "viewer"];
export const canDownloadReports = (role: Role): boolean => REPORT_READERS.includes(role);
