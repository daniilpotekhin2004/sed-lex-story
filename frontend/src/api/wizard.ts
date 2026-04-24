import { apiClient } from "./client";
import type {
  WizardSession,
  WizardDeployResponse,
  WizardExportPackage,
  WizardStoryInput,
  WizardStepResponse,
  WizardStepRunRequest,
  Project,
  WizardStep7DeployOverride,
} from "../shared/types";

export async function createWizardSession(payload: {
  project_id?: string | null;
  story_input: WizardStoryInput;
  auto_run_step1?: boolean;
}): Promise<WizardSession> {
  const response = await apiClient.post<WizardSession>("/v1/wizard/sessions", payload);
  return response.data;
}

export async function getWizardSession(sessionId: string): Promise<WizardSession> {
  const response = await apiClient.get<WizardSession>(`/v1/wizard/sessions/${sessionId}`);
  return response.data;
}

export async function getLatestWizardSession(projectId: string): Promise<WizardSession> {
  const response = await apiClient.get<WizardSession>(`/v1/wizard/sessions/latest`, {
    params: { project_id: projectId },
  });
  return response.data;
}

export async function updateWizardSession(
  sessionId: string,
  payload: { story_input?: WizardStoryInput },
): Promise<WizardSession> {
  const response = await apiClient.patch<WizardSession>(`/v1/wizard/sessions/${sessionId}`, payload);
  return response.data;
}

export async function deleteWizardSession(sessionId: string): Promise<void> {
  await apiClient.delete(`/v1/wizard/sessions/${sessionId}`);
}

export async function getWizardStep(
  sessionId: string,
  step: number,
): Promise<WizardStepResponse> {
  const response = await apiClient.get<WizardStepResponse>(
    `/v1/wizard/sessions/${sessionId}/steps/${step}`,
  );
  return response.data;
}

export async function saveWizardStep(
  sessionId: string,
  step: number,
  payload: { data: Record<string, unknown>; meta?: Record<string, unknown> },
): Promise<WizardStepResponse> {
  const response = await apiClient.put<WizardStepResponse>(
    `/v1/wizard/sessions/${sessionId}/steps/${step}`,
    payload,
  );
  return response.data;
}

export async function runWizardStep(
  sessionId: string,
  step: number,
  payload: WizardStepRunRequest,
): Promise<WizardStepResponse> {
  const response = await apiClient.post<WizardStepResponse>(
    `/v1/wizard/sessions/${sessionId}/steps/${step}/run`,
    payload,
  );
  return response.data;
}

export async function approveWizardStep(
  sessionId: string,
  step: number,
  payload: { status: "approved" | "rejected"; notes?: string | null },
): Promise<WizardStepResponse> {
  const response = await apiClient.post<WizardStepResponse>(
    `/v1/wizard/sessions/${sessionId}/steps/${step}/approve`,
    payload,
  );
  return response.data;
}

export async function exportWizardSession(sessionId: string): Promise<WizardExportPackage> {
  const response = await apiClient.get<WizardExportPackage>(`/v1/wizard/sessions/${sessionId}/export`);
  return response.data;
}

export async function deployWizardSession(sessionId: string): Promise<WizardDeployResponse> {
  const response = await apiClient.post<WizardDeployResponse>(`/v1/wizard/sessions/${sessionId}/deploy`);
  return response.data;
}

export async function resetWizardProject(sessionId: string): Promise<Project> {
  const response = await apiClient.post<Project>(`/v1/wizard/sessions/${sessionId}/reset-project`);
  return response.data;
}

export async function setWizardStep7DeployOverride(
  sessionId: string,
  payload: { enabled: boolean; reason?: string | null },
): Promise<WizardStep7DeployOverride> {
  const response = await apiClient.post(
    `/v1/wizard/sessions/${sessionId}/step7/deploy-override`,
    payload,
  );
  const meta = (response.data?.meta ?? {}) as Record<string, unknown>;
  const raw = meta["step7_deploy_override"];
  if (!raw || typeof raw !== "object") {
    return { enabled: false };
  }
  return raw as WizardStep7DeployOverride;
}
