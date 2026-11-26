import { apiGet, apiSend, apiSendEmpty } from "../../shared/api";
import type { QualityParameterInfo, QualityProfile, QualityProfileTemplate, QualitySpec, QualityStage } from "../../shared/api";
import type { SpecBody } from "./form";

export const qualityKeys = {
  all: ["quality"] as const,
  parameters: () => [...qualityKeys.all, "parameters"] as const,
  templates: () => [...qualityKeys.all, "templates"] as const,
  profiles: () => [...qualityKeys.all, "profiles"] as const,
  profile: (profileId: string) => [...qualityKeys.all, "profile", profileId] as const,
};

const profilePath = (profileId: string) => `/quality-profiles/${encodeURIComponent(profileId)}`;
const specPath = (profileId: string, stage: QualityStage, parameter: string) =>
  `${profilePath(profileId)}/specs/${encodeURIComponent(stage)}/${encodeURIComponent(parameter)}`;

export const fetchQualityParameters = (signal?: AbortSignal) =>
  apiGet<QualityParameterInfo[]>("/quality-parameters", { signal });

export const fetchQualityTemplates = (signal?: AbortSignal) =>
  apiGet<QualityProfileTemplate[]>("/quality-profile-templates", { signal });

export const fetchQualityProfiles = (signal?: AbortSignal) =>
  apiGet<QualityProfile[]>("/quality-profiles", { signal });

export const fetchQualityProfile = (profileId: string, signal?: AbortSignal) =>
  apiGet<QualityProfile>(profilePath(profileId), { signal });

export interface CreateProfileBody {
  name: string;
  template?: string;
}

export const createQualityProfile = (body: CreateProfileBody) =>
  apiSend<QualityProfile>("POST", "/quality-profiles", body);

export const saveQualitySpec = (profileId: string, stage: QualityStage, parameter: string, body: SpecBody) =>
  apiSend<QualitySpec>("PUT", specPath(profileId, stage, parameter), body);

export const removeQualitySpec = (profileId: string, stage: QualityStage, parameter: string) =>
  apiSendEmpty("DELETE", specPath(profileId, stage, parameter));
