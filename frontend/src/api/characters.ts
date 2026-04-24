import { apiClient } from "./client";
import type { CharacterPreset, GenerationOverrides, LoraRef, SDPromptResponse } from "../shared/types";
import { createAssetGenerationJob } from "./generation";
import { waitForGenerationJob } from "../utils/waitForGenerationJob";

export async function listCharacterPresets(params?: {
  only_public?: boolean;
  only_mine?: boolean;
  character_type?: string;
}): Promise<CharacterPreset[]> {
  const response = await apiClient.get<{ items: CharacterPreset[] }>("/characters/presets", {
    params,
  });
  return response.data.items ?? [];
}

export async function createCharacterPreset(payload: Partial<CharacterPreset>): Promise<CharacterPreset> {
  const response = await apiClient.post<CharacterPreset>("/characters/presets", payload);
  return response.data;
}

export async function getCharacterPreset(presetId: string): Promise<CharacterPreset> {
  const response = await apiClient.get<CharacterPreset>(`/characters/presets/${presetId}`);
  return response.data;
}

function splitJobMetaAndOverrides(input: any): {
  project_id?: string;
  style_profile_id?: string;
  num_variants?: number;
  overrides?: GenerationOverrides;
} {
  if (!input || typeof input !== "object") {
    return {};
  }
  const { project_id, style_profile_id, num_variants, ...rest } = input as Record<string, any>;
  const overrides = Object.keys(rest).length ? (rest as GenerationOverrides) : undefined;
  return { project_id, style_profile_id, num_variants, overrides };
}

export async function updateCharacterPreset(
  presetId: string,
  payload: Partial<CharacterPreset>,
  opts?: { unsafe?: boolean },
): Promise<CharacterPreset> {
  const response = await apiClient.put<CharacterPreset>(`/characters/presets/${presetId}`, payload, {
    params: opts ?? {},
  });
  return response.data;
}

export async function listProjectCharacters(projectId: string): Promise<CharacterPreset[]> {
  const response = await apiClient.get<{ items: CharacterPreset[] }>(`/characters/projects/${projectId}/characters`);
  return response.data.items ?? [];
}

export async function importCharacterPreset(projectId: string, presetId: string): Promise<CharacterPreset> {
  const response = await apiClient.post<CharacterPreset>(`/characters/projects/${projectId}/characters/import`, null, {
    params: { preset_id: presetId },
  });
  return response.data;
}

export async function deleteCharacterPreset(presetId: string): Promise<void> {
  await apiClient.delete(`/characters/presets/${presetId}`);
}

export async function generateCharacterSketch(presetId: string): Promise<CharacterPreset> {
  const job = await createAssetGenerationJob({
    task_type: "character_sketch",
    entity_type: "character",
    entity_id: presetId,
  });
  const finalJob = await waitForGenerationJob(job.id);
  if (finalJob.status !== "done") {
    throw new Error(finalJob.error || "Character sketch generation failed");
  }
  return getCharacterPreset(presetId);
}

/**
 * Generate and store a multi-view character reference sheet.
 * (Back-end: POST /characters/presets/:id/sheet)
 */
export async function generateCharacterSheet(
  presetId: string,
  overrides?: any,
): Promise<CharacterPreset> {
  const split = splitJobMetaAndOverrides(overrides);
  const job = await createAssetGenerationJob({
    task_type: "character_sheet",
    entity_type: "character",
    entity_id: presetId,
    project_id: split.project_id,
    style_profile_id: split.style_profile_id,
    overrides: split.overrides,
    num_variants: split.num_variants,
  });
  const finalJob = await waitForGenerationJob(job.id);
  if (finalJob.status !== "done") {
    throw new Error(finalJob.error || "Character sheet generation failed");
  }
  return getCharacterPreset(presetId);
}

export async function regenerateCharacterReference(
  presetId: string,
  kind: string,
  overrides?: any,
): Promise<CharacterPreset> {
  const split = splitJobMetaAndOverrides(overrides);
  const job = await createAssetGenerationJob({
    task_type: "character_reference",
    entity_type: "character",
    entity_id: presetId,
    project_id: split.project_id,
    style_profile_id: split.style_profile_id,
    overrides: split.overrides,
    num_variants: split.num_variants,
    kind,
  });
  const finalJob = await waitForGenerationJob(job.id);
  if (finalJob.status !== "done") {
    throw new Error(finalJob.error || "Character reference generation failed");
  }
  return getCharacterPreset(presetId);
}

export async function uploadCharacterReference(
  presetId: string,
  kind: string,
  file: File,
  options?: { setAsPreview?: boolean; unsafe?: boolean },
): Promise<CharacterPreset> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("set_as_preview", String(options?.setAsPreview ?? true));
  const response = await apiClient.post<CharacterPreset>(`/characters/presets/${presetId}/references/${kind}/upload`, formData, {
    params: options?.unsafe ? { unsafe: true } : undefined,
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data;
}

export async function generateCharacterRepresentation(
  presetId: string,
  payload: {
    kind: string;
    label?: string;
    count?: number;
    prompt_override?: string;
    negative_prompt?: string;
    width?: number;
    height?: number;
    steps?: number;
    cfg_scale?: number;
    seed?: number | null;
    sampler?: string;
    scheduler?: string;
    model_id?: string;
    vae_id?: string;
    loras?: LoraRef[];
    pipeline_profile_id?: string;
    pipeline_profile_version?: number;
  },
): Promise<CharacterPreset> {
  const job = await createAssetGenerationJob({
    task_type: "character_render",
    entity_type: "character",
    entity_id: presetId,
    style_profile_id: (payload as any)?.style_profile_id,
    project_id: (payload as any)?.project_id,
    payload,
  });
  const finalJob = await waitForGenerationJob(job.id);
  if (finalJob.status !== "done") {
    throw new Error(finalJob.error || "Character representation generation failed");
  }
  return getCharacterPreset(presetId);
}

export async function generateCombinedPrompt(payload: {
  prompt: string;
  character_ids: string[];
  style?: string;
  num_variants?: number;
  width?: number;
  height?: number;
  steps?: number;
  cfg_scale?: number;
  seed?: number | null;
}): Promise<SDPromptResponse> {
  const response = await apiClient.post<SDPromptResponse>("/characters/generate-prompt", payload);
  return response.data;
}
