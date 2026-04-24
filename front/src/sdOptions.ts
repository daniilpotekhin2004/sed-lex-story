import { apiClient } from "./client";
import type { SceneNodeCharacter } from "../shared/types";

// Add a single character with detailed configuration
export async function addSceneCharacter(
  sceneId: string,
  payload: {
    character_preset_id: string;
    scene_context?: string | null;
    position?: string | null;
    importance?: number;
    seed_override?: string | null;
    in_frame?: boolean;
    material_set_id?: string | null;
  },
): Promise<SceneNodeCharacter> {
  const response = await apiClient.post<SceneNodeCharacter>(`/v1/scenes/${sceneId}/characters`, payload);
  return response.data;
}

export async function updateSceneCharacterLink(
  sceneId: string,
  linkId: string,
  payload: Partial<{
    scene_context: string | null;
    position: string | null;
    importance: number;
    seed_override: string | null;
    in_frame: boolean;
    material_set_id: string | null;
  }>,
): Promise<SceneNodeCharacter> {
  const response = await apiClient.patch<SceneNodeCharacter>(
    `/v1/scenes/${sceneId}/characters/${linkId}`,
    payload,
  );
  return response.data;
}

export async function deleteSceneCharacterLink(sceneId: string, linkId: string): Promise<void> {
  await apiClient.delete(`/v1/scenes/${sceneId}/characters/${linkId}`);
}

// Attach multiple presets by issuing multiple calls
export async function attachCharactersToScene(
  sceneId: string,
  characterPresetIds: string[],
): Promise<number> {
  let attached = 0;
  for (const id of characterPresetIds) {
    await addSceneCharacter(sceneId, { character_preset_id: id });
    attached += 1;
  }
  return attached;
}

export async function listSceneCharacters(sceneId: string): Promise<SceneNodeCharacter[]> {
  const response = await apiClient.get<SceneNodeCharacter[]>(`/v1/scenes/${sceneId}/characters`);
  return response.data;
}
