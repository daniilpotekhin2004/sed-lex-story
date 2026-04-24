/**
 * Scene Composition API
 * 
 * Generates AI-powered composition prompts for scene slides using img2img workflow.
 */

import { apiClient } from "./client";

export interface CompositionPromptRequest {
  scene_id: string;
  slide_visual: string;
  cast_ids: string[];
  slide_id?: string;
  location_id?: string;
  has_location_reference?: boolean;
  framing?: "full" | "half" | "portrait";
}

export interface CompositionPromptResponse {
  composition_prompt: string;
  location_ref_url?: string;
  character_ref_urls: string[];
}

/**
 * Generate composition prompt for a scene slide
 */
export async function generateCompositionPrompt(
  sceneId: string,
  request: Omit<CompositionPromptRequest, "scene_id">
): Promise<CompositionPromptResponse> {
  const response = await apiClient.post<CompositionPromptResponse>(
    `/v1/scenes/${sceneId}/composition-prompt`,
    {
      scene_id: sceneId,
      ...request,
    }
  );
  return response.data;
}
