import { apiClient } from "./client";
import type {
  AdminOverviewResponse,
  AdminUserListResponse,
  CohortUpdateRequest,
  CohortUpdateResult,
  ComfyOverviewResponse,
  ErrorFeedResponse,
  RoleAuditListResponse,
  RoleBulkUpdateRequest,
  RoleBulkUpdateResponse,
  RoleUpdateRequest,
  RoleUpdateResult,
  UserStatsResponse,
} from "../shared/types";

type ListUsersParams = {
  search?: string;
  role?: string;
  registered_from?: string;
  registered_to?: string;
  activity_from?: string;
  activity_to?: string;
  page?: number;
  page_size?: number;
};

export async function listAdminUsers(params: ListUsersParams = {}): Promise<AdminUserListResponse> {
  const response = await apiClient.get<AdminUserListResponse>("/v1/admin/users", { params });
  return response.data;
}

export async function updateUserRole(userId: string, payload: RoleUpdateRequest): Promise<RoleUpdateResult> {
  const response = await apiClient.post<RoleUpdateResult>(`/v1/admin/users/${userId}/role`, payload);
  return response.data;
}

export async function updateUserCohort(userId: string, payload: CohortUpdateRequest): Promise<CohortUpdateResult> {
  const response = await apiClient.post<CohortUpdateResult>(`/v1/admin/users/${userId}/cohort`, payload);
  return response.data;
}

export async function bulkUpdateUserRoles(payload: RoleBulkUpdateRequest): Promise<RoleBulkUpdateResponse> {
  const response = await apiClient.post<RoleBulkUpdateResponse>("/v1/admin/users/roles/bulk", payload);
  return response.data;
}

export async function getAdminOverview(): Promise<AdminOverviewResponse> {
  const response = await apiClient.get<AdminOverviewResponse>("/v1/admin/overview");
  return response.data;
}

export async function getComfyOverview(): Promise<ComfyOverviewResponse> {
  const response = await apiClient.get<ComfyOverviewResponse>("/v1/admin/comfy");
  return response.data;
}

export async function getRoleAudit(params: { page?: number; page_size?: number } = {}): Promise<RoleAuditListResponse> {
  const response = await apiClient.get<RoleAuditListResponse>("/v1/admin/audit/roles", { params });
  return response.data;
}

export async function getErrorFeed(limit = 80): Promise<ErrorFeedResponse> {
  const response = await apiClient.get<ErrorFeedResponse>("/v1/admin/errors", { params: { limit } });
  return response.data;
}

export async function getAdminUserStats(userId: string): Promise<UserStatsResponse> {
  const response = await apiClient.get<UserStatsResponse>(`/v1/admin/users/${userId}/stats`);
  return response.data;
}

export async function getMyRoleStats(): Promise<UserStatsResponse> {
  const response = await apiClient.get<UserStatsResponse>("/v1/admin/me/stats");
  return response.data;
}
