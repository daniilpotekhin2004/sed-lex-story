import { apiClient } from "./client";
import type { User } from "../shared/types";

export type LoginPayload = { username: string; password: string };
export type LoginResponse = { access_token: string; refresh_token: string; token_type: string };
export type RegisterPayload = { username: string; email: string; password: string; full_name?: string | null };
export type RefreshResponse = LoginResponse;

export async function login(payload: LoginPayload): Promise<LoginResponse> {
  const response = await apiClient.post<LoginResponse>("/auth/login", payload);
  return response.data;
}

export async function refresh(refreshToken: string): Promise<RefreshResponse> {
  const response = await apiClient.post<RefreshResponse>("/auth/refresh", {
    refresh_token: refreshToken,
  });
  return response.data;
}

export async function registerPlayer(payload: RegisterPayload): Promise<User> {
  const response = await apiClient.post<User>("/auth/register", payload);
  return response.data;
}

export async function getMe(): Promise<User> {
  const response = await apiClient.get<User>("/auth/me");
  return response.data;
}
