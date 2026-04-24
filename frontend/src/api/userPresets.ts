import { apiClient } from "./client";
import type {
  UserGenerationPreset,
  UserPresetListResponse,
  UserPresetCreate,
  UserPresetUpdate,
} from "../shared/types";

export async function listUserPresets(): Promise<UserPresetListResponse> {
  const { data } = await apiClient.get<UserPresetListResponse>("/user-presets");
  return data;
}

export async function createUserPreset(payload: UserPresetCreate): Promise<UserGenerationPreset> {
  const { data } = await apiClient.post<UserGenerationPreset>("/user-presets", payload);
  return data;
}

export async function updateUserPreset(
  presetId: string,
  payload: UserPresetUpdate,
): Promise<UserGenerationPreset> {
  const { data } = await apiClient.patch<UserGenerationPreset>(`/user-presets/${presetId}`, payload);
  return data;
}

export async function deleteUserPreset(presetId: string): Promise<void> {
  await apiClient.delete(`/user-presets/${presetId}`);
}

export async function touchUserPreset(presetId: string): Promise<UserGenerationPreset> {
  const { data } = await apiClient.post<UserGenerationPreset>(`/user-presets/${presetId}/touch`);
  return data;
}
