import { apiClient } from "./client";
import type { StyleProfile } from "../shared/types";

export async function listStyleProfiles(projectId?: string): Promise<StyleProfile[]> {
  const params = projectId ? { project_id: projectId } : {};
  const response = await apiClient.get<StyleProfile[]>("/v1/style-profiles", { params });
  return response.data ?? [];
}

export async function createStyleProfile(payload: {
  project_id: string;
  name: string;
  description?: string | null;
  base_prompt?: string | null;
  negative_prompt?: string | null;
  cfg_scale?: number | null;
  steps?: number | null;
  resolution?: { width?: number; height?: number } | null;
  sampler?: string | null;
  model_checkpoint?: string | null;
  lora_refs?: Record<string, unknown>[] | null;
  seed_policy?: string | null;
  palette?: string[] | null;
  forbidden?: string[] | null;
  style_metadata?: Record<string, unknown> | null;
}): Promise<StyleProfile> {
  const response = await apiClient.post<StyleProfile>("/v1/style-profiles", payload);
  return response.data;
}

export async function getStyleProfile(profileId: string): Promise<StyleProfile> {
  const response = await apiClient.get<StyleProfile>(`/v1/style-profiles/${profileId}`);
  return response.data;
}

export async function updateStyleProfile(
  profileId: string,
  payload: Partial<{
    name: string;
    description?: string | null;
    base_prompt?: string | null;
    negative_prompt?: string | null;
    cfg_scale?: number | null;
    steps?: number | null;
    resolution?: { width?: number; height?: number } | null;
    sampler?: string | null;
    model_checkpoint?: string | null;
    lora_refs?: Record<string, unknown>[] | null;
    seed_policy?: string | null;
    palette?: string[] | null;
    forbidden?: string[] | null;
    style_metadata?: Record<string, unknown> | null;
  }>,
): Promise<StyleProfile> {
  const response = await apiClient.patch<StyleProfile>(`/v1/style-profiles/${profileId}`, payload);
  return response.data;
}

export async function bootstrapLegalStyleProfiles(projectId: string, overwrite: boolean = false): Promise<StyleProfile[]> {
  const response = await apiClient.post<StyleProfile[]>("/v1/style-profiles/bootstrap/legal", {
    project_id: projectId,
    overwrite,
  });
  return response.data ?? [];
}
