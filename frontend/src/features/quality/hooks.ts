import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { QualityStage } from "../../shared/api";
import {
  createQualityProfile,
  fetchQualityParameters,
  fetchQualityProfile,
  fetchQualityProfiles,
  fetchQualityTemplates,
  qualityKeys,
  removeQualitySpec,
  saveQualitySpec,
} from "./api";
import type { CreateProfileBody } from "./api";
import type { SpecBody } from "./form";

// The catalog and the presets are static server-side data.
export const useQualityParametersQuery = () =>
  useQuery({
    queryKey: qualityKeys.parameters(),
    queryFn: ({ signal }) => fetchQualityParameters(signal),
    staleTime: Infinity,
  });

export const useQualityTemplatesQuery = () =>
  useQuery({
    queryKey: qualityKeys.templates(),
    queryFn: ({ signal }) => fetchQualityTemplates(signal),
    staleTime: Infinity,
  });

export const useQualityProfilesQuery = () =>
  useQuery({ queryKey: qualityKeys.profiles(), queryFn: ({ signal }) => fetchQualityProfiles(signal) });

export const useQualityProfileQuery = (profileId: string) =>
  useQuery({
    queryKey: qualityKeys.profile(profileId),
    queryFn: ({ signal }) => fetchQualityProfile(profileId, signal),
  });

export function useCreateQualityProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateProfileBody) => createQualityProfile(body),
    onSuccess: async (profile) => {
      queryClient.setQueryData(qualityKeys.profile(profile.id), profile);
      await queryClient.invalidateQueries({ queryKey: qualityKeys.profiles() });
    },
  });
}

/** A spec write answers with the spec only, so the profile and the list (spec counts) are refetched. */
function useSpecMutation<Variables>(mutationFn: (variables: Variables) => Promise<unknown>, profileId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: qualityKeys.profile(profileId) }),
        queryClient.invalidateQueries({ queryKey: qualityKeys.profiles() }),
      ]),
  });
}

export const useSaveQualitySpec = (profileId: string) =>
  useSpecMutation(
    (variables: { stage: QualityStage; parameter: string; body: SpecBody }) =>
      saveQualitySpec(profileId, variables.stage, variables.parameter, variables.body),
    profileId,
  );

export const useRemoveQualitySpec = (profileId: string) =>
  useSpecMutation(
    (variables: { stage: QualityStage; parameter: string }) =>
      removeQualitySpec(profileId, variables.stage, variables.parameter),
    profileId,
  );
