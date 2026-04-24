import { apiClient } from "./client";
import type { ProjectRelease, ReleaseAssignedUser } from "../shared/types";

export async function listProjectReleases(projectId: string): Promise<ProjectRelease[]> {
  const response = await apiClient.get<{ items: ProjectRelease[] }>(`/v1/projects/${projectId}/releases`);
  return response.data.items ?? [];
}

export async function listProjectReleaseCandidateUsers(
  projectId: string,
  params: { search?: string; limit?: number } = {},
): Promise<ReleaseAssignedUser[]> {
  const response = await apiClient.get<{ items: ReleaseAssignedUser[] }>(
    `/v1/projects/${projectId}/releases/candidate-users`,
    { params },
  );
  return response.data.items ?? [];
}

export async function publishProjectRelease(
  projectId: string,
  payload: { graph_id?: string; notes?: string | null },
): Promise<ProjectRelease> {
  const response = await apiClient.post<ProjectRelease>(`/v1/projects/${projectId}/releases/publish`, payload);
  return response.data;
}

export async function replaceProjectReleaseAccess(
  projectId: string,
  releaseId: string,
  payload: { user_ids: string[]; cohort_codes: string[] },
): Promise<ProjectRelease> {
  const response = await apiClient.put<ProjectRelease>(`/v1/projects/${projectId}/releases/${releaseId}/access`, payload);
  return response.data;
}

export async function archiveProjectRelease(projectId: string, releaseId: string): Promise<ProjectRelease> {
  const response = await apiClient.post<ProjectRelease>(`/v1/projects/${projectId}/releases/${releaseId}/archive`);
  return response.data;
}
