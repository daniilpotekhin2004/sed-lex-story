import { apiClient } from "./client";
import type { PromptBundle } from "../shared/types";

export async function getPromptPreview(sceneId: string): Promise<PromptBundle> {
  const response = await apiClient.get<PromptBundle>(`/v1/scenes/${sceneId}/prompt-preview`);
  return response.data;
}
