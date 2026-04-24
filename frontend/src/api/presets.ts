import { apiClient } from "./client";
import type { PresetList } from "../shared/types";

export async function getPresets(): Promise<PresetList> {
  const response = await apiClient.get<PresetList>("/presets");
  return response.data;
}
