import { apiClient } from "./client";
import type { OpsStatusResponse, ServiceControlResult } from "../shared/types";

export async function listServices(): Promise<OpsStatusResponse> {
  const response = await apiClient.get<OpsStatusResponse>("/v1/ops/services");
  return response.data;
}

export async function controlService(
  serviceId: string,
  action: "start" | "restart" | "stop",
): Promise<ServiceControlResult> {
  const response = await apiClient.post<ServiceControlResult>(`/v1/ops/services/${serviceId}/control`, {
    action,
  });
  return response.data;
}
