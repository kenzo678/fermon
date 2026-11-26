import { describe, expect, it } from "vitest";
import type { Role } from "../../shared/api";
import {
  canAcknowledgeAlerts,
  canConfigureTanks,
  canDownloadReports,
  canManageUsers,
  canRecordLabAnalyses,
  canWriteBatches,
  canWriteQualityProfiles,
} from "./permissions";

// Mirrors backend/src/fermon/identity/domain/role.py: keep both tables in step.
const TABLE: Array<[string, (role: Role) => boolean, Record<Role, boolean>]> = [
  ["canManageUsers", canManageUsers, { admin: true, brewer: false, viewer: false }],
  ["canConfigureTanks", canConfigureTanks, { admin: true, brewer: false, viewer: false }],
  ["canWriteBatches", canWriteBatches, { admin: true, brewer: true, viewer: false }],
  ["canAcknowledgeAlerts", canAcknowledgeAlerts, { admin: true, brewer: true, viewer: false }],
  ["canWriteQualityProfiles", canWriteQualityProfiles, { admin: true, brewer: true, viewer: false }],
  ["canRecordLabAnalyses", canRecordLabAnalyses, { admin: true, brewer: true, viewer: false }],
  ["canDownloadReports", canDownloadReports, { admin: true, brewer: true, viewer: true }],
];

describe("permissions", () => {
  it.each(TABLE)("%s matches the backend rule for every role", (_name, check, expected) => {
    for (const role of ["admin", "brewer", "viewer"] as const) {
      expect(check(role)).toBe(expected[role]);
    }
  });
});
