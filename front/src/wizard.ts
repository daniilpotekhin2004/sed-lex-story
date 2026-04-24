import { apiClient } from "./client";

export async function createTextualInversion(payload: {
  token: string;
  character_id?: string | null;
  init_text?: string | null;
  num_vectors?: number;
  overwrite?: boolean;
}): Promise<{ token: string; created: boolean; info?: Record<string, unknown> | null }> {
  const response = await apiClient.post("/v1/training/textual-inversion", payload);
  return response.data;
}

export async function prepareLoraTraining(payload: {
  material_set_id: string;
  token: string;
  label?: string | null;
  caption?: string | null;
  character_id?: string | null;
}): Promise<{
  dataset_path: string;
  image_count: number;
  token: string;
  label: string;
  material_set_id: string;
}> {
  const response = await apiClient.post("/v1/training/lora", payload);
  return response.data;
}
