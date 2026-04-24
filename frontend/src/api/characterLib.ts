import { apiClient } from "./client";
import type { CharacterLibList } from "../shared/types";

export async function listCharacterLibrary(params?: {
  page?: number;
  page_size?: number;
  include_public?: boolean;
}): Promise<CharacterLibList> {
  const response = await apiClient.get<CharacterLibList>("/v1/character-lib", { params });
  return response.data;
}
