import { apiClient } from "./client";
import type { LegalConcept } from "../shared/types";

export async function listLegalConcepts(): Promise<LegalConcept[]> {
  const response = await apiClient.get<{ items: LegalConcept[] }>("/v1/legal");
  return response.data.items ?? [];
}

export async function createLegalConcept(payload: {
  code: string;
  title: string;
  description?: string;
  difficulty?: number;
  tags?: string[];
}): Promise<LegalConcept> {
  const response = await apiClient.post<LegalConcept>("/v1/legal", payload);
  return response.data;
}

export async function getLegalConcept(conceptId: string): Promise<LegalConcept> {
  const response = await apiClient.get<LegalConcept>(`/v1/legal/${conceptId}`);
  return response.data;
}

export async function attachLegalConceptToScene(
  conceptId: string,
  sceneId: string,
): Promise<{ success: boolean }> {
  const response = await apiClient.post(`/v1/legal/${conceptId}/attach`, { scene_id: sceneId });
  return response.data;
}
