import { useQuery } from "@tanstack/react-query";
import { getPresets } from "../api/presets";
import { listProjectCharacters } from "../api/characters";
import type { PresetList, PresetOption } from "../shared/types";

export function usePresets(projectId?: string) {
  return useQuery({
    queryKey: ["presets", projectId],
    queryFn: async () => {
      const base = await getPresets();
      if (!projectId) return base;
      const characters = await listProjectCharacters(projectId);
      const characterItems: PresetOption[] = characters.map((character) => ({
        id: character.id,
        name: character.name,
        description: character.description || undefined,
        preview_thumbnail_url: character.preview_thumbnail_url || character.preview_image_url || undefined,
      }));
      const merged: PresetList = { ...base, characters: characterItems };
      return merged;
    },
  });
}
