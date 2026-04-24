import { apiClient } from "./client";
import type {
  GenerationParams,
  GenerationResponse,
  TaskListResponse,
  TaskStatus,
  PromptBundle,
  ImageVariant,
  GenerationJob,
} from "../shared/types";

// Prompt analysis types
export interface PromptAnalysis {
  original: string;
  translated: string;
  non_english_count: number;
  needs_translation: boolean;
  warning: string | null;
  translation_changed: boolean;
}

export interface TranslateResponse {
  prompt: PromptAnalysis;
  negative_prompt: PromptAnalysis | null;
}

export type AssetGenerationJobCreate = {
  task_type: string;
  entity_type: string;
  entity_id: string;
  project_id?: string | null;
  style_profile_id?: string | null;
  kind?: string | null;
  overrides?: Record<string, unknown> | null;
  payload?: Record<string, unknown> | null;
  num_variants?: number;
};

// Analyze prompt for non-English content
export async function analyzePrompt(prompt: string): Promise<PromptAnalysis> {
  const response = await apiClient.post<PromptAnalysis>("/v1/prompt/analyze", { prompt });
  return response.data;
}

// Translate prompt and negative prompt
export async function translatePrompt(
  prompt: string,
  negativePrompt?: string,
): Promise<TranslateResponse> {
  const response = await apiClient.post<TranslateResponse>("/v1/prompt/translate", {
    prompt,
    negative_prompt: negativePrompt,
  });
  return response.data;
}

// Legacy generation endpoint
export async function generateImage(payload: GenerationParams): Promise<GenerationResponse> {
  const response = await apiClient.post<GenerationResponse>("/generation/generate", payload);
  return response.data;
}

// V1: Generate with PromptEngine (default) or raw prompt
export async function generateSceneImage(
  sceneId: string,
  payload: {
    use_prompt_engine?: boolean;
    prompt?: string;
    negative_prompt?: string;
    num_variants?: number;
    width?: number;
    height?: number;
    cfg_scale?: number;
    steps?: number;
    seed?: number;
    seed_policy?: "fixed" | "random" | "derived" | "character-consistent";
    style_profile_id?: string;
    pipeline?: {
      mode?: "standard" | "controlnet";
      cast_ids?: string[];
      framing?: "full" | "half" | "portrait";
      pose_image_url?: string;
      identity_mode?: "reference" | "ip_adapter";
      location_ref_mode?: "auto" | "none" | "selected";
      location_ref_url?: string;
      character_slot_ids?: string[];
    };
    slide_id?: string;
    auto_approve?: boolean;
  } = {},
): Promise<GenerationJob> {
  const response = await apiClient.post<GenerationJob>(
    `/v1/scenes/${sceneId}/generate`,
    { use_prompt_engine: true, ...payload },
    { timeout: 300000 },
  );
  return response.data;
}

// V1: Preview generated prompt from PromptEngine
export async function previewScenePrompt(
  sceneId: string,
  options: { characterIds?: string[] } = {},
): Promise<PromptBundle> {
  const params: Record<string, string> = {};
  if (options.characterIds) {
    params.character_ids = options.characterIds.length > 0 ? options.characterIds.join(",") : "none";
  }
  const response = await apiClient.get<PromptBundle>(`/v1/scenes/${sceneId}/prompt-preview`, { params });
  return response.data;
}

// V1: Get generated images for a scene
export async function getSceneImages(sceneId: string): Promise<ImageVariant[]> {
  const response = await apiClient.get<{ items: ImageVariant[] }>(`/v1/scenes/${sceneId}/images`);
  return response.data.items ?? [];
}

export async function approveSceneImage(sceneId: string, variantId: string): Promise<ImageVariant> {
  const response = await apiClient.post<ImageVariant>(`/v1/scenes/${sceneId}/images/${variantId}/approve`);
  return response.data;
}

export async function deleteSceneImage(sceneId: string, variantId: string): Promise<void> {
  await apiClient.delete(`/v1/scenes/${sceneId}/images/${variantId}`);
}

export async function getGenerationJob(jobId: string): Promise<GenerationJob> {
  const response = await apiClient.get<GenerationJob>(`/v1/generation-jobs/${jobId}`);
  return response.data;
}

// V1: Unified asset generation job enqueue
export async function createAssetGenerationJob(payload: AssetGenerationJobCreate): Promise<GenerationJob> {
  const response = await apiClient.post<GenerationJob>(`/v1/generation/jobs`, payload, {
    timeout: 300000,
  });
  return response.data;
}

// V1: Unified job status (assets + scenes)
export async function getUnifiedGenerationJob(jobId: string): Promise<GenerationJob> {
  const response = await apiClient.get<GenerationJob>(`/v1/generation/jobs/${jobId}`);
  return response.data;
}

export async function getTaskStatus(taskId: string): Promise<TaskStatus> {
  const response = await apiClient.get<TaskStatus>(`/generation/tasks/${taskId}`);
  return response.data;
}

export async function listTasks(
  params: { page?: number; page_size?: number; status?: string } = {},
): Promise<TaskListResponse> {
  const response = await apiClient.get<TaskListResponse>("/generation/tasks", { params });
  return response.data;
}

export async function runPipelineCheck(): Promise<TaskStatus> {
  const response = await apiClient.post<TaskStatus>("/generation/pipeline-check");
  return response.data;
}
