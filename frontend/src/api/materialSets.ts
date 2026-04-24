import { apiClient } from "./client";
import type { MaterialSet } from "../shared/types";

export async function listMaterialSets(
  projectId: string,
  params: { asset_type?: "character" | "location"; asset_id?: string } = {},
): Promise<MaterialSet[]> {
  const response = await apiClient.get<{ items: MaterialSet[] }>(`/v1/projects/${projectId}/material-sets`, {
    params,
  });
  return response.data.items ?? [];
}

export async function createMaterialSet(
  projectId: string,
  payload: {
    asset_type: "character" | "location";
    asset_id: string;
    label: string;
    reference_images?: MaterialSet["reference_images"];
    material_metadata?: MaterialSet["material_metadata"];
  },
): Promise<MaterialSet> {
  const response = await apiClient.post<MaterialSet>(`/v1/projects/${projectId}/material-sets`, payload);
  return response.data;
}
