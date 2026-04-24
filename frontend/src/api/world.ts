import { apiClient } from "./client";
import type { Artifact, DocumentTemplate, GenerationJob, GenerationOverrides, Location, StyleBible } from "../shared/types";
import { createAssetGenerationJob } from "./generation";

export async function getStyleBible(projectId: string): Promise<StyleBible> {
  const response = await apiClient.get<StyleBible>(`/v1/projects/${projectId}/style-bible`);
  return response.data;
}

export async function upsertStyleBible(projectId: string, payload: Partial<StyleBible>): Promise<StyleBible> {
  const response = await apiClient.put<StyleBible>(`/v1/projects/${projectId}/style-bible`, payload);
  return response.data;
}

export async function listLocations(projectId: string): Promise<Location[]> {
  const response = await apiClient.get<{ items: Location[] }>(`/v1/projects/${projectId}/locations`);
  return response.data.items ?? [];
}

export async function createLocation(projectId: string, payload: Partial<Location>): Promise<Location> {
  const response = await apiClient.post<Location>(`/v1/projects/${projectId}/locations`, payload);
  return response.data;
}

export async function getLocation(locationId: string): Promise<Location> {
  const response = await apiClient.get<Location>(`/v1/locations/${locationId}`);
  return response.data;
}

export async function getArtifact(artifactId: string): Promise<Artifact> {
  const response = await apiClient.get<Artifact>(`/v1/artifacts/${artifactId}`);
  return response.data;
}

export async function updateLocation(
  locationId: string,
  payload: Partial<Location>,
  opts?: { unsafe?: boolean },
): Promise<Location> {
  const response = await apiClient.patch<Location>(`/v1/locations/${locationId}`, payload, {
    params: opts ?? {},
  });
  return response.data;
}

export async function deleteLocation(locationId: string): Promise<void> {
  await apiClient.delete(`/v1/locations/${locationId}`);
}

export async function generateLocationSketch(
  locationId: string,
  overrides?: GenerationOverrides,
  opts?: { projectId?: string },
): Promise<GenerationJob> {
  return createAssetGenerationJob({
    task_type: "location_sketch",
    entity_type: "location",
    entity_id: locationId,
    project_id: opts?.projectId,
    overrides: overrides ?? undefined,
  });
}

/**
 * Generate and store a small reference set (establishing/interior/detail) for a location.
 * (Back-end: POST /v1/locations/:id/sheet)
 */
export async function generateLocationSheet(
  locationId: string,
  overrides?: GenerationOverrides,
  opts?: { projectId?: string },
): Promise<GenerationJob> {
  return createAssetGenerationJob({
    task_type: "location_sheet",
    entity_type: "location",
    entity_id: locationId,
    project_id: opts?.projectId,
    overrides: overrides ?? undefined,
  });
}

export async function uploadLocationPreview(
  locationId: string,
  file: File,
  opts?: { unsafe?: boolean },
): Promise<Location> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await apiClient.post<Location>(`/v1/locations/${locationId}/preview/upload`, formData, {
    params: opts?.unsafe ? { unsafe: true } : undefined,
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data;
}

export async function uploadLocationReference(
  locationId: string,
  kind: string,
  file: File,
  opts?: { unsafe?: boolean; setAsPreview?: boolean },
): Promise<Location> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("set_as_preview", String(opts?.setAsPreview ?? false));
  const response = await apiClient.post<Location>(`/v1/locations/${locationId}/references/${kind}/upload`, formData, {
    params: opts?.unsafe ? { unsafe: true } : undefined,
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data;
}

export async function listArtifacts(projectId: string): Promise<Artifact[]> {
  const response = await apiClient.get<{ items: Artifact[] }>(`/v1/projects/${projectId}/artifacts`);
  return response.data.items ?? [];
}

export async function createArtifact(projectId: string, payload: Partial<Artifact>): Promise<Artifact> {
  const response = await apiClient.post<Artifact>(`/v1/projects/${projectId}/artifacts`, payload);
  return response.data;
}

export async function updateArtifact(
  artifactId: string,
  payload: Partial<Artifact>,
  opts?: { unsafe?: boolean },
): Promise<Artifact> {
  const response = await apiClient.patch<Artifact>(`/v1/artifacts/${artifactId}`, payload, {
    params: opts ?? {},
  });
  return response.data;
}

export async function deleteArtifact(artifactId: string): Promise<void> {
  await apiClient.delete(`/v1/artifacts/${artifactId}`);
}

export async function generateArtifactSketch(
  artifactId: string,
  overrides?: GenerationOverrides,
  opts?: { projectId?: string },
): Promise<GenerationJob> {
  return createAssetGenerationJob({
    task_type: "artifact_sketch",
    entity_type: "artifact",
    entity_id: artifactId,
    overrides: overrides ?? undefined,
    project_id: opts?.projectId,
  });
}

export async function uploadArtifactPreview(
  artifactId: string,
  file: File,
  opts?: { unsafe?: boolean },
): Promise<Artifact> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await apiClient.post<Artifact>(`/v1/artifacts/${artifactId}/preview/upload`, formData, {
    params: opts?.unsafe ? { unsafe: true } : undefined,
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data;
}

export async function listDocumentTemplates(projectId: string): Promise<DocumentTemplate[]> {
  const response = await apiClient.get<{ items: DocumentTemplate[] }>(
    `/v1/projects/${projectId}/document-templates`,
  );
  return response.data.items ?? [];
}

export async function createDocumentTemplate(
  projectId: string,
  payload: Partial<DocumentTemplate>,
): Promise<DocumentTemplate> {
  const response = await apiClient.post<DocumentTemplate>(
    `/v1/projects/${projectId}/document-templates`,
    payload,
  );
  return response.data;
}

export async function updateDocumentTemplate(
  templateId: string,
  payload: Partial<DocumentTemplate>,
  opts?: { unsafe?: boolean },
): Promise<DocumentTemplate> {
  const response = await apiClient.patch<DocumentTemplate>(`/v1/document-templates/${templateId}`, payload, {
    params: opts ?? {},
  });
  return response.data;
}

export async function importLocation(projectId: string, locationId: string): Promise<Location> {
  const response = await apiClient.post<Location>(`/v1/projects/${projectId}/locations/import`, null, {
    params: { location_id: locationId },
  });
  return response.data;
}

export async function importArtifact(projectId: string, artifactId: string): Promise<Artifact> {
  const response = await apiClient.post<Artifact>(`/v1/projects/${projectId}/artifacts/import`, null, {
    params: { artifact_id: artifactId },
  });
  return response.data;
}

export async function importDocumentTemplate(projectId: string, templateId: string): Promise<DocumentTemplate> {
  const response = await apiClient.post<DocumentTemplate>(`/v1/projects/${projectId}/document-templates/import`, null, {
    params: { template_id: templateId },
  });
  return response.data;
}

export async function listStudioLocations(params?: { only_public?: boolean; only_mine?: boolean }): Promise<Location[]> {
  const response = await apiClient.get<{ items: Location[] }>("/v1/studio/locations", { params });
  return response.data.items ?? [];
}

export async function createStudioLocation(payload: Partial<Location>): Promise<Location> {
  const response = await apiClient.post<Location>("/v1/studio/locations", payload);
  return response.data;
}

export async function updateStudioLocation(locationId: string, payload: Partial<Location>): Promise<Location> {
  const response = await apiClient.patch<Location>(`/v1/studio/locations/${locationId}`, payload);
  return response.data;
}

export async function deleteStudioLocation(locationId: string): Promise<void> {
  await apiClient.delete(`/v1/studio/locations/${locationId}`);
}

export async function listStudioArtifacts(params?: { only_public?: boolean; only_mine?: boolean }): Promise<Artifact[]> {
  const response = await apiClient.get<{ items: Artifact[] }>("/v1/studio/artifacts", { params });
  return response.data.items ?? [];
}

export async function createStudioArtifact(payload: Partial<Artifact>): Promise<Artifact> {
  const response = await apiClient.post<Artifact>("/v1/studio/artifacts", payload);
  return response.data;
}

export async function updateStudioArtifact(artifactId: string, payload: Partial<Artifact>): Promise<Artifact> {
  const response = await apiClient.patch<Artifact>(`/v1/studio/artifacts/${artifactId}`, payload);
  return response.data;
}

export async function deleteStudioArtifact(artifactId: string): Promise<void> {
  await apiClient.delete(`/v1/studio/artifacts/${artifactId}`);
}

export async function listStudioDocumentTemplates(
  params?: { only_public?: boolean; only_mine?: boolean },
): Promise<DocumentTemplate[]> {
  const response = await apiClient.get<{ items: DocumentTemplate[] }>("/v1/studio/document-templates", { params });
  return response.data.items ?? [];
}

export async function createStudioDocumentTemplate(
  payload: Partial<DocumentTemplate>,
): Promise<DocumentTemplate> {
  const response = await apiClient.post<DocumentTemplate>("/v1/studio/document-templates", payload);
  return response.data;
}

export async function updateStudioDocumentTemplate(
  templateId: string,
  payload: Partial<DocumentTemplate>,
): Promise<DocumentTemplate> {
  const response = await apiClient.patch<DocumentTemplate>(`/v1/studio/document-templates/${templateId}`, payload);
  return response.data;
}

export async function deleteStudioDocumentTemplate(templateId: string): Promise<void> {
  await apiClient.delete(`/v1/studio/document-templates/${templateId}`);
}

export async function deleteDocumentTemplate(templateId: string): Promise<void> {
  await apiClient.delete(`/v1/document-templates/${templateId}`);
}
