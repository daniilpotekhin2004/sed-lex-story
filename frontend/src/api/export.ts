import { apiClient } from "./client";
import type { ProjectExport } from "../shared/types";

export async function fetchExport(projectId: string): Promise<ProjectExport> {
  const response = await apiClient.get<ProjectExport>(`/v1/projects/${projectId}/export`);
  return response.data;
}
