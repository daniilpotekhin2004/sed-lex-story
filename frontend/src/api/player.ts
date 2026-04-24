import { apiClient } from "./client";
import type {
  PlayerCatalogResponse,
  PlayerPackage,
  PlayerProjectStats,
  PlayerResume,
  PlayerRunSyncRequest,
  PlayerRunSyncResponse,
} from "../shared/player";

export async function listPlayableProjects() {
  const response = await apiClient.get<PlayerCatalogResponse>("/v1/player/projects");
  return response.data.items ?? [];
}

export async function fetchPlayerPackage(projectId: string, packageVersion?: string | null) {
  const response = await apiClient.get<PlayerPackage>(`/v1/player/projects/${projectId}/package`, {
    params: packageVersion ? { package_version: packageVersion } : undefined,
  });
  return response.data;
}

export async function syncPlayerRun(projectId: string, payload: PlayerRunSyncRequest) {
  const response = await apiClient.post<PlayerRunSyncResponse>(`/v1/player/projects/${projectId}/runs/sync`, payload);
  return response.data;
}

export async function fetchPlayerProjectStats(projectId: string) {
  const response = await apiClient.get<PlayerProjectStats>(`/v1/player/projects/${projectId}/stats`);
  return response.data;
}

export async function fetchPlayerResume(projectId: string) {
  const response = await apiClient.get<PlayerResume>(`/v1/player/projects/${projectId}/resume`);
  return response.data;
}
