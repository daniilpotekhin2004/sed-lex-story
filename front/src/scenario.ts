import { apiClient } from "./client";
import type {
  Project,
  ProjectVoiceoverLine,
  ProjectVoiceoverRead,
  ProjectVoiceoverRolePrompts,
  ProjectVoiceoverSettings,
  ProjectVoiceoverSummary,
} from "../shared/types";

export async function listProjects(): Promise<Project[]> {
  const response = await apiClient.get<{ items: Project[] }>("/v1/projects");
  return response.data.items ?? [];
}

export async function createProject(payload: { name: string; description?: string | null }): Promise<Project> {
  const response = await apiClient.post<Project>("/v1/projects", payload);
  return response.data;
}

export async function getProject(projectId: string): Promise<Project> {
  const response = await apiClient.get<Project>(`/v1/projects/${projectId}`);
  return response.data;
}

export async function updateProject(
  projectId: string,
  payload: Partial<{ name: string; description?: string | null; style_profile_id?: string | null }>,
): Promise<Project> {
  const response = await apiClient.patch<Project>(`/v1/projects/${projectId}`, payload);
  return response.data;
}

export async function deleteProject(projectId: string): Promise<void> {
  await apiClient.delete(`/v1/projects/${projectId}`);
}

type GenerateVoiceoverLinePayload = {
  line_id: string;
  language?: string;
  voice_profile?: string | null;
  replace_existing?: boolean;
};

type ApproveVoiceoverLinePayload = {
  line_id: string;
  variant_id: string;
};

type GenerateVoiceoverAllPayload = {
  language?: string;
  default_voice_profile?: string | null;
  replace_existing?: boolean;
  skip_approved?: boolean;
};

type VoiceoverLineActionResponse = {
  project_id: string;
  graph_id: string;
  line: ProjectVoiceoverLine;
  summary: ProjectVoiceoverSummary;
  settings?: ProjectVoiceoverSettings;
  suggested_role_prompts?: ProjectVoiceoverRolePrompts;
};

type UpdateVoiceoverSettingsPayload = Partial<ProjectVoiceoverSettings>;

export async function getProjectVoiceover(projectId: string): Promise<ProjectVoiceoverRead> {
  const response = await apiClient.get<ProjectVoiceoverRead>(`/v1/projects/${projectId}/voiceover`);
  return response.data;
}

export async function generateProjectVoiceoverLine(
  projectId: string,
  payload: GenerateVoiceoverLinePayload,
): Promise<VoiceoverLineActionResponse> {
  const response = await apiClient.post<VoiceoverLineActionResponse>(
    `/v1/projects/${projectId}/voiceover/lines/generate`,
    payload,
  );
  return response.data;
}

export async function approveProjectVoiceoverLine(
  projectId: string,
  payload: ApproveVoiceoverLinePayload,
): Promise<VoiceoverLineActionResponse> {
  const response = await apiClient.post<VoiceoverLineActionResponse>(
    `/v1/projects/${projectId}/voiceover/lines/approve`,
    payload,
  );
  return response.data;
}

export async function generateProjectVoiceoverAll(
  projectId: string,
  payload: GenerateVoiceoverAllPayload,
): Promise<{
  generated_count: number;
  skipped_count: number;
  summary: ProjectVoiceoverSummary;
  settings?: ProjectVoiceoverSettings;
  suggested_role_prompts?: ProjectVoiceoverRolePrompts;
}> {
  const response = await apiClient.post<{
    project_id: string;
    graph_id: string;
    generated_count: number;
    skipped_count: number;
    summary: ProjectVoiceoverSummary;
    settings?: ProjectVoiceoverSettings;
    suggested_role_prompts?: ProjectVoiceoverRolePrompts;
  }>(`/v1/projects/${projectId}/voiceover/generate-all`, payload);
  return {
    generated_count: response.data.generated_count,
    skipped_count: response.data.skipped_count,
    summary: response.data.summary,
    settings: response.data.settings,
    suggested_role_prompts: response.data.suggested_role_prompts,
  };
}

export async function updateProjectVoiceoverSettings(
  projectId: string,
  payload: UpdateVoiceoverSettingsPayload,
): Promise<{
  settings: ProjectVoiceoverSettings;
  suggested_role_prompts?: ProjectVoiceoverRolePrompts;
  updated_at?: string | null;
}> {
  const response = await apiClient.patch<{
    project_id: string;
    graph_id: string;
    settings: ProjectVoiceoverSettings;
    suggested_role_prompts?: ProjectVoiceoverRolePrompts;
    updated_at?: string | null;
  }>(`/v1/projects/${projectId}/voiceover/settings`, payload);
  return {
    settings: response.data.settings,
    suggested_role_prompts: response.data.suggested_role_prompts,
    updated_at: response.data.updated_at,
  };
}
